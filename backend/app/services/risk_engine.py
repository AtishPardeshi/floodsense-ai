"""Integration layer for flood risk scoring in FloodSense AI.

Orchestrates the deterministic physical baseline (PhysicalRiskModel) and optional
trained machine-learning model (MLRiskModel).
Preserves 100% backward compatibility with existing public API endpoints and test contracts.
"""
from __future__ import annotations

from typing import Any

from app.core import constants as c
from app.database.schemas import Level, Rainfall, Spot, SpotRisk
from app.services.ml_risk_model import MLRiskModel
from app.services.physical_risk import PhysicalRiskModel
from app.services.terrain_service import TerrainService

# Initialize shared singleton instances
_terrain_service = TerrainService()
_physical_model = PhysicalRiskModel()
_ml_model = MLRiskModel()


def effective_intensity(rain: Rainfall) -> float:
    """Delegates to PhysicalRiskModel for effective rain intensity (mm/h)."""
    return _physical_model.calculate_effective_intensity(rain)


def susceptibility(spot: Spot) -> float:
    """Delegates to PhysicalRiskModel for intrinsic location susceptibility."""
    res, _, _ = _physical_model.calculate_susceptibility(spot)
    return res


def level_for(risk: float) -> Level:
    """Maps continuous risk score to alert category."""
    return _physical_model.level_for_score(risk)


def score_spot(spot: Spot, rain: Rainfall) -> SpotRisk:
    """Evaluates physical risk for a single spot and returns backward-compatible SpotRisk."""
    # Lookup slope from terrain service if available
    elev_res = _terrain_service.get_elevation(spot.lat, spot.lng)
    slope = elev_res.slope_pct if elev_res.status == "available" else None

    # Calculate physical risk baseline
    phys_res = _physical_model.predict_spot(spot, rain, slope_pct=slope)

    final_risk = phys_res.physical_score
    final_level = phys_res.risk_level

    # If ML model is loaded and validated, integrate it
    if _ml_model.is_loaded:
        ml_features = {
            "rain_1h_mm": rain.rain_1h_mm,
            "rain_3h_mm": rain.rain_3h_mm,
            "forecast_2h_mm": rain.forecast_2h_mm,
            "rel_depth_m": spot.rel_depth_m,
            "catchment_ha": spot.catchment_ha,
            "drain_dist_m": spot.drain_dist_m,
            "slope_pct": slope or 1.0,
        }
        ml_score = _ml_model.predict_risk(ml_features)
        if ml_score is not None:
            # Weighted ensemble: 70% physical baseline + 30% ML
            final_risk = round(0.70 * phys_res.physical_score + 0.30 * ml_score, 3)
            final_level = level_for(final_risk)

    return SpotRisk(
        spot_id=spot.id,
        name=spot.name,
        lat=spot.lat,
        lng=spot.lng,
        risk=final_risk,
        level=final_level,
        lead_time_min=phys_res.lead_time_min,
        drivers=phys_res.contributing_factors,
    )


def score_all(spots: list[Spot], rain: Rainfall) -> list[SpotRisk]:
    """Scores all spots and returns list sorted descending by risk score."""
    return sorted((score_spot(s, rain) for s in spots), key=lambda r: r.risk, reverse=True)
