"""Historical Storm Replay Engine for FloodSense AI.

Simulates the chronological progression of documented historical storms
using cached hourly rainfall and the production physical risk engine.
Actual incident labels are strictly isolated from model prediction inputs
and exposed only in the retrospective outcome comparison overlay.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app.database.schemas import Rainfall, Spot
from app.demo.fixtures import SPOTS
from app.demo.scenarios import HISTORICAL_SCENARIOS, ScenarioDefinition
from app.services.physical_risk import PhysicalRiskModel
from app.services.terrain_service import TerrainService

ROOT = Path(__file__).resolve().parents[3]
BY_ID = {s.id: s for s in SPOTS}


@dataclass
class SpotReplayState:
    spot_id: str
    name: str
    lat: float
    lng: float
    predicted_risk: float
    predicted_level: str
    lead_time_min: int | None
    drivers: list[str]
    rain_1h_mm: float
    rain_3h_mm: float
    rain_24h_mm: float
    data_quality_status: str
    retrospective_outcome: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayState:
    run_id: str
    event_id: str
    scenario_name: str
    current_step: int
    total_steps: int
    timestamp: str
    is_paused: bool
    is_completed: bool
    max_rainfall_rate_mm_h: float
    spots: list[dict[str, Any]]
    active_incidents_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReplaySession:
    """Manages an individual historical replay simulation session."""

    def __init__(
        self,
        scenario: ScenarioDefinition,
        run_id: str | None = None,
        features_path: Path | None = None,
        incidents_path: Path | None = None,
    ):
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.scenario = scenario
        self.features_path = features_path or (ROOT / "data" / "processed" / "features.csv")
        self.incidents_path = incidents_path or (ROOT / "data" / "raw" / "incidents.csv")

        self.physical_model = PhysicalRiskModel()
        self.terrain_service = TerrainService()

        self._load_data()
        self.current_step = 0
        self.is_paused = False
        self.is_completed = False

    @property
    def total_steps(self) -> int:
        return len(self.timeline)

    def _load_data(self) -> None:
        if not self.features_path.exists():
            raise FileNotFoundError(f"Features file {self.features_path} does not exist.")

        features_df = pd.read_csv(self.features_path)
        features_df["timestamp"] = pd.to_datetime(features_df["timestamp"])

        start_ts = pd.Timestamp(self.scenario.start_time)
        end_ts = pd.Timestamp(self.scenario.end_time)

        # Slice time window
        mask = (features_df["timestamp"] >= start_ts) & (features_df["timestamp"] <= end_ts)
        self.storm_features = features_df[mask].sort_values("timestamp")
        self.timeline: list[pd.Timestamp] = sorted(self.storm_features["timestamp"].unique())

        if not self.timeline:
            raise ValueError(f"No rainfall features found for scenario time window {start_ts} to {end_ts}")

        # Load incidents for retrospective overlay
        self.incidents_by_spot_hour: dict[tuple[str, str], dict[str, Any]] = {}
        if self.incidents_path.exists():
            inc_df = pd.read_csv(self.incidents_path)
            for inc in inc_df.itertuples():
                spot_id = getattr(inc, "spot_id", "")
                dt_str = str(getattr(inc, "datetime", "") or getattr(inc, "date", ""))
                if dt_str:
                    onset = pd.Timestamp(dt_str[:19]).floor("h")
                    # Window +/- 1h around onset
                    for offset in [-1, 0, 1]:
                        window_ts = (onset + pd.Timedelta(hours=offset)).isoformat()
                        self.incidents_by_spot_hour[(spot_id, window_ts)] = {
                            "actual_flood": True,
                            "severity": int(getattr(inc, "severity", 2)),
                            "incident_id": getattr(inc, "incident_id", ""),
                            "event_id": getattr(inc, "event_id", ""),
                            "source_name": getattr(inc, "source_name", ""),
                            "source_url": getattr(inc, "source_url", ""),
                            "notes": getattr(inc, "notes", ""),
                        }

    def get_state(self) -> ReplayState:
        """Computes model predictions and outcome overlay at the current timestamp."""
        if not self.timeline:
            raise ValueError("Replay timeline is empty.")

        current_ts = self.timeline[self.current_step]
        ts_str = current_ts.isoformat()
        current_data = self.storm_features[self.storm_features["timestamp"] == current_ts]

        spot_states: list[dict[str, Any]] = []
        max_rain = 0.0
        active_incidents = 0

        for spot in SPOTS:
            spot_row = current_data[current_data["spot_id"] == spot.id]
            if not spot_row.empty:
                r_val = spot_row.iloc[0]
                rain_1h = float(r_val["rain_1h_mm"])
                rain_3h = float(r_val["rain_3h_mm"])
                rain_6h = float(getattr(r_val, "rain_6h_mm", 0.0) or 0.0)
                rain_24h = float(r_val["rain_24h_mm"])
            else:
                rain_1h = rain_3h = rain_6h = rain_24h = 0.0

            if rain_1h > max_rain:
                max_rain = rain_1h

            # Terrain slope
            elev_res = self.terrain_service.get_elevation(spot.lat, spot.lng)
            slope = elev_res.slope_pct if elev_res.status == "available" else None

            # Physical model prediction (Strictly NO actual-label leakage)
            rain_input = Rainfall(
                rain_1h_mm=rain_1h,
                rain_3h_mm=rain_3h,
                rain_6h_mm=rain_6h,
                forecast_2h_mm=0.0,
            )
            prediction = self.physical_model.predict_spot(spot, rain_input, slope_pct=slope)

            # Retrospective outcome lookup (isolated from prediction)
            retrospective = self.incidents_by_spot_hour.get(
                (spot.id, ts_str),
                {"actual_flood": False, "severity": None, "incident_id": None},
            )
            if retrospective.get("actual_flood"):
                active_incidents += 1

            spot_state = SpotReplayState(
                spot_id=spot.id,
                name=spot.name,
                lat=spot.lat,
                lng=spot.lng,
                predicted_risk=prediction.physical_score,
                predicted_level=prediction.risk_level,
                lead_time_min=prediction.lead_time_min,
                drivers=prediction.contributing_factors,
                rain_1h_mm=rain_1h,
                rain_3h_mm=rain_3h,
                rain_24h_mm=rain_24h,
                data_quality_status=prediction.data_quality.get("status", "high"),
                retrospective_outcome=retrospective,
            )
            spot_states.append(spot_state.to_dict())

        return ReplayState(
            run_id=self.run_id,
            event_id=self.scenario.event_id,
            scenario_name=self.scenario.name,
            current_step=self.current_step,
            total_steps=len(self.timeline),
            timestamp=ts_str,
            is_paused=self.is_paused,
            is_completed=self.is_completed,
            max_rainfall_rate_mm_h=round(max_rain, 1),
            spots=spot_states,
            active_incidents_count=active_incidents,
        )

    def next_step(self) -> ReplayState:
        """Advances replay by one hourly timestep."""
        if self.current_step < len(self.timeline) - 1:
            self.current_step += 1
            if self.current_step == len(self.timeline) - 1:
                self.is_completed = True
        else:
            self.is_completed = True
        return self.get_state()

    def pause(self) -> ReplayState:
        self.is_paused = True
        return self.get_state()

    def resume(self) -> ReplayState:
        self.is_paused = False
        return self.get_state()

    def reset(self) -> ReplayState:
        self.current_step = 0
        self.is_paused = False
        self.is_completed = False
        return self.get_state()


class ReplayManager:
    """Manages active in-memory replay sessions."""

    def __init__(self):
        self._sessions: dict[str, ReplaySession] = {}

    def list_available_events(self) -> list[dict[str, Any]]:
        return [sc.to_dict() for sc in HISTORICAL_SCENARIOS.values()]

    def start_session(self, event_id: str) -> ReplaySession:
        if event_id not in HISTORICAL_SCENARIOS:
            raise KeyError(f"Unknown event_id: '{event_id}'. Available: {list(HISTORICAL_SCENARIOS.keys())}")
        scenario = HISTORICAL_SCENARIOS[event_id]
        session = ReplaySession(scenario=scenario)
        self._sessions[session.run_id] = session
        return session

    def get_session(self, run_id: str) -> ReplaySession:
        if run_id not in self._sessions:
            raise KeyError(f"Replay run_id '{run_id}' not found.")
        return self._sessions[run_id]


# Global singleton manager
replay_manager = ReplayManager()
