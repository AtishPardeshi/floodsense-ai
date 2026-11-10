"""API router for operational evidence overlays based on human-verified citizen reports."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Query, status

from app.database.models import OperationalEvidenceResponse
from app.services.evidence_service import evidence_service

router = APIRouter(prefix="/evidence", tags=["operational_evidence"])


@router.get("", response_model=list[OperationalEvidenceResponse])
def get_all_operational_evidence(
    radius_meters: float = Query(default=1500.0, ge=100, le=10000, description="Spatial proximity in meters"),
    window_hours: float = Query(default=6.0, ge=0.5, le=72.0, description="Time window in hours"),
    as_of: str | None = Query(default=None, description="ISO timestamp for historical as-of evaluation"),
) -> list[OperationalEvidenceResponse]:
    """Retrieves operational evidence overlay signals for all monitored pilot spots.

    Isolates physical modeling from crowd evidence; pending reports are counted separately.
    """
    return evidence_service.get_all_spots_evidence(
        radius_meters=radius_meters,
        window_hours=window_hours,
        as_of_time=as_of,
    )


@router.get("/{spot_id}", response_model=OperationalEvidenceResponse)
def get_spot_operational_evidence(
    spot_id: str,
    radius_meters: float = Query(default=1500.0, ge=100, le=10000, description="Spatial proximity in meters"),
    window_hours: float = Query(default=6.0, ge=0.5, le=72.0, description="Time window in hours"),
    as_of: str | None = Query(default=None, description="ISO timestamp for historical as-of evaluation"),
) -> OperationalEvidenceResponse:
    """Retrieves operational evidence overlay signal for an individual pilot spot."""
    try:
        return evidence_service.get_spot_evidence(
            spot_id=spot_id,
            radius_meters=radius_meters,
            window_hours=window_hours,
            as_of_time=as_of,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

