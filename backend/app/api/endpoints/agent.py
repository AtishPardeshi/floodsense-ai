"""API endpoints for AI Early-Warning Agent & Advisory Orchestrator."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Body

from app.database.schemas import Rainfall, SpotRisk
from app.demo.fixtures import SPOTS
from app.services.agent_service import early_warning_agent
from app.services.risk_engine import score_all
from app.services.weather_service import weather_service

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/advisory")
def generate_advisory(
    spots: list[dict[str, Any]] = Body(default=[]),
    scenario_name: str | None = None,
) -> dict[str, Any]:
    """Generates structured municipal action plan and bilingual citizen advisories."""
    if not spots:
        # Default to dry weather evaluation
        evaluated = score_all(SPOTS, Rainfall())
        spots = [s.model_dump() for s in evaluated]

    advisory = early_warning_agent.generate_advisory(spots, scenario_name=scenario_name)
    return advisory.to_dict()


@router.get("/advisory/live")
def get_live_advisory() -> dict[str, Any]:
    """Generates emergency advisory directly from current live weather and spot risks."""
    live_risks = weather_service.get_live_risk()
    advisory = early_warning_agent.generate_advisory(live_risks, scenario_name="Bengaluru Live Weather Feed")
    return advisory.to_dict()

