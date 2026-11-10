from fastapi import APIRouter, Query

from app.database.schemas import Rainfall, Spot, SpotRisk
from app.demo.fixtures import SPOTS
from app.services.risk_engine import score_all

router = APIRouter()


@router.get("/spots", response_model=list[Spot])
def list_spots() -> list[Spot]:
    return SPOTS


@router.get("/risk", response_model=list[SpotRisk])
def get_risk(
    rain_1h_mm: float = Query(0, ge=0, le=200),
    rain_3h_mm: float = Query(0, ge=0, le=500),
    forecast_2h_mm: float = Query(0, ge=0, le=300),
) -> list[SpotRisk]:
    rain = Rainfall(rain_1h_mm=rain_1h_mm, rain_3h_mm=rain_3h_mm, forecast_2h_mm=forecast_2h_mm)
    return score_all(SPOTS, rain)
