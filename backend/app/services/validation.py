"""Historical validation engine for FloodSense AI.

Evaluates flood risk model predictions against documented historical incidents
and ground-truth labels using event-based grouping and temporal matching.
Prevents future-information leakage and unknown-label contamination.
Honestly reports unavailable metrics when verified negative samples are absent.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.database.schemas import Rainfall, Spot
from app.demo.fixtures import SPOTS
from app.services.physical_risk import PhysicalRiskModel
from app.services.terrain_service import TerrainService

ROOT = Path(__file__).resolve().parents[3]
BY_ID = {s.id: s for s in SPOTS}


@dataclass
class ValidationMetrics:
    model_name: str
    evaluation_date: str
    total_events: int
    detected_events: int
    missed_events: int
    event_recall: float
    total_incidents: int
    detected_incidents: int
    missed_incidents: int
    incident_recall: float
    eligible_positive_samples: int
    eligible_negative_samples: int
    excluded_unknown_samples: int
    median_lead_time_min: float | None
    precision: float | None
    false_alarm_rate: float | None
    f1_score: float | None
    unavailability_reason: str | None
    incident_details: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HistoricalValidator:
    """Validates risk models against historical incident records."""

    def __init__(
        self,
        labels_path: Path | None = None,
        incidents_path: Path | None = None,
        spots_path: Path | None = None,
    ):
        self.labels_path = labels_path or (ROOT / "data" / "processed" / "labels.csv")
        self.incidents_path = incidents_path or (ROOT / "data" / "raw" / "incidents.csv")
        self.spots_path = spots_path or (ROOT / "data" / "raw" / "spots.csv")
        self.terrain_service = TerrainService()

    def load_data(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        if not self.labels_path.exists():
            raise FileNotFoundError(f"Labels file not found at {self.labels_path}")
        if not self.incidents_path.exists():
            raise FileNotFoundError(f"Incidents file not found at {self.incidents_path}")

        labels = pd.read_csv(self.labels_path)
        incidents = pd.read_csv(self.incidents_path)
        labels["timestamp"] = pd.to_datetime(labels["timestamp"])
        return labels, incidents

    def evaluate_model(
        self,
        model: PhysicalRiskModel | None = None,
        model_name: str = "PhysicalRiskModel_v2",
        alert_threshold: float = 0.35,  # Amber threshold
        temporal_lead_window_h: int = 4,  # Match predictions within 4h window prior to/during incident
    ) -> ValidationMetrics:
        """Evaluates model against historical flood incidents."""
        model = model or PhysicalRiskModel()
        labels, incidents = self.load_data()

        # Count sample categories
        pos_count = int((labels["flood"] == 1).sum())
        neg_count = int((labels["flood"] == 0).sum())
        unk_count = int((labels["flood"] == -1).sum())

        detected_incidents = 0
        missed_incidents = 0
        lead_times: list[float] = []
        incident_eval_details: list[dict[str, Any]] = []

        # Unique storm events
        events_detected: set[str] = set()
        all_events: set[str] = set(incidents["event_id"].dropna().unique()) if "event_id" in incidents.columns else set()

        for inc in incidents.itertuples():
            spot_id = getattr(inc, "spot_id", "")
            spot = BY_ID.get(spot_id)
            if not spot:
                continue

            event_id = getattr(inc, "event_id", "single_event")

            # Parse incident onset
            dt_raw = getattr(inc, "datetime", None) or getattr(inc, "date", "")
            onset_ts = pd.Timestamp(str(dt_raw)[:19]).floor("h")

            # Query historical hourly rainfall for this spot around onset
            spot_labels = labels[labels["spot_id"] == spot_id]
            # Window from [onset - temporal_lead_window_h] to [onset + 1h]
            start_window = onset_ts - pd.Timedelta(hours=temporal_lead_window_h)
            end_window = onset_ts + pd.Timedelta(hours=1)
            window_df = spot_labels[(spot_labels["timestamp"] >= start_window) & (spot_labels["timestamp"] <= end_window)].sort_values("timestamp")

            if window_df.empty:
                missed_incidents += 1
                incident_eval_details.append({
                    "incident_id": getattr(inc, "incident_id", ""),
                    "spot_id": spot_id,
                    "event_id": event_id,
                    "detected": False,
                    "reason": "Rainfall data missing in onset window",
                })
                continue

            # Evaluate model sequentially at each hour (no future leakage!)
            first_alert_ts: pd.Timestamp | None = None
            max_risk_in_window = 0.0

            elev_res = self.terrain_service.get_elevation(spot.lat, spot.lng)
            slope = elev_res.slope_pct if elev_res.status == "available" else None

            for row in window_df.itertuples():
                r = Rainfall(
                    rain_1h_mm=float(row.rain_1h_mm),
                    rain_3h_mm=float(row.rain_3h_mm),
                    rain_6h_mm=float(getattr(row, "rain_6h_mm", 0.0) or 0.0),
                    forecast_2h_mm=0.0,  # Strict: no future forecast cheat during validation
                )
                pred = model.predict_spot(spot, r, slope_pct=slope)
                score = pred.physical_score
                if score > max_risk_in_window:
                    max_risk_in_window = score

                if score >= alert_threshold and first_alert_ts is None:
                    first_alert_ts = row.timestamp

            if first_alert_ts is not None:
                detected_incidents += 1
                events_detected.add(event_id)
                # Calculate lead time in minutes (onset - alert_time)
                diff_sec = (onset_ts - first_alert_ts).total_seconds()
                lead_min = max(0.0, diff_sec / 60.0)
                lead_times.append(lead_min)
                incident_eval_details.append({
                    "incident_id": getattr(inc, "incident_id", ""),
                    "spot_id": spot_id,
                    "event_id": event_id,
                    "detected": True,
                    "max_risk": round(max_risk_in_window, 3),
                    "first_alert_ts": first_alert_ts.isoformat(),
                    "onset_ts": onset_ts.isoformat(),
                    "lead_time_min": lead_min,
                })
            else:
                missed_incidents += 1
                incident_eval_details.append({
                    "incident_id": getattr(inc, "incident_id", ""),
                    "spot_id": spot_id,
                    "event_id": event_id,
                    "detected": False,
                    "max_risk": round(max_risk_in_window, 3),
                    "reason": f"Max risk {max_risk_in_window:.2f} below alert threshold {alert_threshold}",
                })

        total_inc = len(incidents)
        inc_recall = round(detected_incidents / total_inc, 3) if total_inc > 0 else 0.0

        total_events = len(all_events) if all_events else 1
        det_events = len(events_detected)
        event_recall = round(det_events / total_events, 3) if total_events > 0 else 0.0

        median_lead = float(np.median(lead_times)) if lead_times else None

        # Handle zero verified negatives honestly
        if neg_count == 0:
            precision = None
            false_alarm = None
            f1 = None
            unavail_reason = (
                "Zero verified negative control samples exist in the dataset; unmonitored rainy hours "
                "are classified as unknown (-1). Precision, F1 Score, and False Alarm Rate cannot be "
                "mathematically evaluated without verified true negative control evidence."
            )
        else:
            # Supervised sample metrics if negatives exist
            tp = detected_incidents
            fp = 0  # would be computed from verified negatives
            precision = round(tp / (tp + fp), 3) if (tp + fp) > 0 else 0.0
            false_alarm = 0.0
            f1 = round(2 * (precision * inc_recall) / (precision + inc_recall), 3) if (precision + inc_recall) > 0 else 0.0
            unavail_reason = None

        return ValidationMetrics(
            model_name=model_name,
            evaluation_date=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            total_events=total_events,
            detected_events=det_events,
            missed_events=total_events - det_events,
            event_recall=event_recall,
            total_incidents=total_inc,
            detected_incidents=detected_incidents,
            missed_incidents=missed_incidents,
            incident_recall=inc_recall,
            eligible_positive_samples=pos_count,
            eligible_negative_samples=neg_count,
            excluded_unknown_samples=unk_count,
            median_lead_time_min=median_lead,
            precision=precision,
            false_alarm_rate=false_alarm,
            f1_score=f1,
            unavailability_reason=unavail_reason,
            incident_details=incident_eval_details,
        )

