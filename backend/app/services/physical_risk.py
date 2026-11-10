"""Transparent deterministic physical risk engine for FloodSense AI.

Calculates urban flood susceptibility and dynamic risk from physical variables:
  - Dynamic rainfall intensity & multi-hour accumulation (1h, 3h, 6h, 24h)
  - Topographical depression depth (m below surrounding crest)
  - Upstream catchment area (hectares)
  - Distance to nearest stormwater drain (m)
  - Local terrain slope (% grade)
  - Historical flood incident frequency

Handles missing terrain/drainage data safely with dynamic weight normalization.
Never treats missing features as measured zeroes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

from app.core import constants as c
from app.database.schemas import Level, Rainfall, Spot

# Normalization caps for physical variables
MAX_DEPTH_M = 6.0
MAX_CATCHMENT_HA = 300.0
MAX_DRAIN_DIST_M = 400.0
MAX_INCIDENTS = 5.0
FLAT_SLOPE_THRESHOLD_PCT = 3.0  # Slope <= 3% indicates severe runoff accumulation risk

# Base physical weights (must sum to 1.0)
DEFAULT_WEIGHTS = {
    "depression": 0.30,  # Gravity depression/valley dip
    "catchment": 0.20,   # Upstream drainage area
    "drain": 0.20,       # Distance to municipal drain or canal
    "history": 0.15,     # Past documented incidents
    "slope": 0.15,       # Terrain flat/incline factor (flat = higher risk)
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


@dataclass
class PhysicalRiskResult:
    spot_id: str
    name: str
    lat: float
    lng: float
    physical_score: float
    risk_level: Level
    lead_time_min: int | None
    contributing_factors: list[str]
    data_quality: dict[str, Any]
    model_version: str = "physical_v2.0"
    effective_intensity_mm_h: float = 0.0

    def to_spot_risk_dict(self) -> dict[str, Any]:
        """Backward-compatible dictionary matching the existing SpotRisk schema."""
        return {
            "spot_id": self.spot_id,
            "name": self.name,
            "lat": self.lat,
            "lng": self.lng,
            "risk": round(self.physical_score, 3),
            "level": self.risk_level,
            "lead_time_min": self.lead_time_min,
            "drivers": self.contributing_factors,
        }


class PhysicalRiskModel:
    """Configurable physical urban flood risk model."""

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = dict(weights or DEFAULT_WEIGHTS)
        total_w = sum(self.weights.values())
        if not math.isclose(total_w, 1.0, rel_tol=1e-3):
            # Normalize to 1.0
            self.weights = {k: v / total_w for k, v in self.weights.items()}

    def calculate_effective_intensity(self, rain: Rainfall) -> float:
        """Computes effective rainfall intensity in mm/h from recent and forecast rain."""
        rain_1h = getattr(rain, "rain_1h_mm", 0.0) or 0.0
        rain_3h = getattr(rain, "rain_3h_mm", 0.0) or 0.0
        rain_6h = getattr(rain, "rain_6h_mm", 0.0) or 0.0
        forecast_2h = getattr(rain, "forecast_2h_mm", 0.0) or 0.0

        # Weighted combination of immediate intensity, recent accumulation, and forecast
        eff = (
            0.45 * rain_1h
            + 0.25 * (rain_3h / 3.0)
            + 0.10 * (rain_6h / 6.0)
            + 0.20 * (forecast_2h / 2.0)
        )
        return max(0.0, eff)

    def calculate_susceptibility(
        self,
        spot: Spot,
        slope_pct: float | None = None,
    ) -> tuple[float, list[str], dict[str, Any]]:
        """Calculates intrinsic location susceptibility score (0.0 to 1.0).

        Safely re-normalizes weights if slope or other terrain metrics are missing.
        """
        drivers: list[str] = []
        active_weights = dict(self.weights)
        missing_inputs: list[str] = []
        partial_scores: dict[str, float] = {}

        # 1. Depression depth
        if hasattr(spot, "rel_depth_m") and spot.rel_depth_m is not None:
            depth_ratio = _clamp(spot.rel_depth_m / MAX_DEPTH_M)
            partial_scores["depression"] = depth_ratio
            if spot.rel_depth_m >= 3.0:
                drivers.append(f"Sits {spot.rel_depth_m:.1f} m below surrounding crest")
        else:
            missing_inputs.append("rel_depth_m")
            active_weights.pop("depression", None)

        # 2. Upstream Catchment
        if hasattr(spot, "catchment_ha") and spot.catchment_ha is not None:
            catchment_ratio = _clamp(spot.catchment_ha / MAX_CATCHMENT_HA)
            partial_scores["catchment"] = catchment_ratio
            if spot.catchment_ha >= 150.0:
                drivers.append(f"Large upstream drainage catchment ({spot.catchment_ha:.0f} ha)")
        else:
            missing_inputs.append("catchment_ha")
            active_weights.pop("catchment", None)

        # 3. Drain Distance
        if hasattr(spot, "drain_dist_m") and spot.drain_dist_m is not None:
            drain_ratio = _clamp(spot.drain_dist_m / MAX_DRAIN_DIST_M)
            partial_scores["drain"] = drain_ratio
            if spot.drain_dist_m >= 200.0:
                drivers.append(f"Nearest stormwater drain is {spot.drain_dist_m:.0f} m away")
        else:
            missing_inputs.append("drain_dist_m")
            active_weights.pop("drain", None)

        # 4. Past Incidents
        if hasattr(spot, "past_incidents") and spot.past_incidents is not None:
            inc_ratio = _clamp(spot.past_incidents / MAX_INCIDENTS)
            partial_scores["history"] = inc_ratio
            if spot.past_incidents >= 2:
                drivers.append(f"{spot.past_incidents} past documented flood events")
        else:
            missing_inputs.append("past_incidents")
            active_weights.pop("history", None)

        # 5. Local Slope
        if slope_pct is not None:
            # Flatter terrain carries higher ponding risk: 0% slope -> 1.0 risk factor, >=3% slope -> 0.0
            slope_score = _clamp((FLAT_SLOPE_THRESHOLD_PCT - slope_pct) / FLAT_SLOPE_THRESHOLD_PCT)
            partial_scores["slope"] = slope_score
            if slope_pct < 1.2:
                drivers.append(f"Flat topography ({slope_pct:.1f}% slope) impedes runoff drainage")
        else:
            missing_inputs.append("slope_pct")
            active_weights.pop("slope", None)

        # Dynamic re-normalization if any input is missing
        total_active_w = sum(active_weights.values())
        if total_active_w <= 0.0:
            susceptibility = 0.5  # Neutral fallback if all inputs missing
            quality_status = "unavailable"
        else:
            normalized_w = {k: v / total_active_w for k, v in active_weights.items()}
            susceptibility = sum(partial_scores[k] * normalized_w[k] for k in active_weights)
            quality_status = "high" if not missing_inputs else ("partial" if len(missing_inputs) <= 2 else "low")

        data_quality = {
            "status": quality_status,
            "active_features": list(active_weights.keys()),
            "missing_features": missing_inputs,
            "weights_used": active_weights,
        }
        return susceptibility, drivers, data_quality

    def level_for_score(self, score: float) -> Level:
        if score >= c.RED_THRESHOLD:
            return "red"
        if score >= c.AMBER_THRESHOLD:
            return "amber"
        return "green"

    def predict_spot(
        self,
        spot: Spot,
        rain: Rainfall,
        slope_pct: float | None = None,
    ) -> PhysicalRiskResult:
        """Calculates physical flood risk for a spot under given rainfall."""
        eff_intensity = self.calculate_effective_intensity(rain)
        susceptibility, drivers, quality = self.calculate_susceptibility(spot, slope_pct=slope_pct)

        # Rain factor non-linear scale (0 to 1)
        rain_factor = _clamp(eff_intensity / c.EXTREME_RAIN_MM_H) ** 0.8
        raw_score = rain_factor * (0.35 + 0.9 * susceptibility)
        score = _clamp(raw_score, 0.0, 1.0)
        level = self.level_for_score(score)

        if eff_intensity >= 20.0:
            drivers.insert(0, f"Heavy rainfall intensity (~{eff_intensity:.0f} mm/h effective)")
        elif eff_intensity >= 10.0:
            drivers.insert(0, f"Moderate rainfall intensity (~{eff_intensity:.0f} mm/h effective)")

        # Evaluate current rainfall without forecast to compute warning lead time
        rain_now_only = Rainfall(
            rain_1h_mm=getattr(rain, "rain_1h_mm", 0.0),
            rain_3h_mm=getattr(rain, "rain_3h_mm", 0.0),
            forecast_2h_mm=0.0,
        )
        now_intensity = self.calculate_effective_intensity(rain_now_only)
        now_factor = _clamp(now_intensity / c.EXTREME_RAIN_MM_H) ** 0.8
        now_score = _clamp(now_factor * (0.35 + 0.9 * susceptibility), 0.0, 1.0)
        now_level = self.level_for_score(now_score)

        rank = {"green": 0, "amber": 1, "red": 2}
        if rank[level] > rank[now_level]:
            lead_time = c.FORECAST_LEAD_MIN  # 45 minutes lead
        elif level != "green":
            lead_time = 0  # Inundation threshold already reached
        else:
            lead_time = None

        return PhysicalRiskResult(
            spot_id=spot.id,
            name=spot.name,
            lat=spot.lat,
            lng=spot.lng,
            physical_score=round(score, 3),
            risk_level=level,
            lead_time_min=lead_time,
            contributing_factors=drivers,
            data_quality=quality,
            model_version="physical_v2.0",
            effective_intensity_mm_h=round(eff_intensity, 1),
        )

    def predict_all(
        self,
        spots: list[Spot],
        rain: Rainfall,
        slopes: dict[str, float | None] | None = None,
    ) -> list[PhysicalRiskResult]:
        """Calculates risk across all spots, sorted descending by risk score."""
        slopes = slopes or {}
        results = [self.predict_spot(s, rain, slope_pct=slopes.get(s.id)) for s in spots]
        return sorted(results, key=lambda r: r.physical_score, reverse=True)

