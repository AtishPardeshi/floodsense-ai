from typing import Literal
from pydantic import BaseModel, Field

Level = Literal["green", "amber", "red"]


class Spot(BaseModel):
    id: str
    name: str
    lat: float
    lng: float
    rel_depth_m: float = Field(ge=0, description="Depth below surroundings (m)")
    catchment_ha: float = Field(ge=0, description="Upstream catchment (hectares)")
    drain_dist_m: float = Field(ge=0, description="Distance to nearest drain (m)")
    past_incidents: int = Field(ge=0, description="Recorded past flood events")


class Rainfall(BaseModel):
    rain_1h_mm: float = Field(default=0, ge=0)
    rain_3h_mm: float = Field(default=0, ge=0)
    forecast_2h_mm: float = Field(default=0, ge=0)


class SpotRisk(BaseModel):
    spot_id: str
    name: str
    lat: float
    lng: float
    risk: float
    level: Level
    lead_time_min: int | None
    drivers: list[str]
