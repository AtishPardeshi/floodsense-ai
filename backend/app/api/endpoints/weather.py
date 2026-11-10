"""API endpoints for Live Weather Ingestion."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter

from app.services.weather_service import weather_service

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/live")
def get_live_weather(force: bool = False) -> dict[str, Any]:
    """Fetches real-time precipitation and nowcast for Bengaluru pilot spots."""
    summary = weather_service.get_live_weather(force_refresh=force)
    return summary.to_dict()


@router.get("/risk")
def get_live_risk() -> list[dict[str, Any]]:
    """Evaluates physical risk across all spots using current live weather conditions."""
    return weather_service.get_live_risk()

