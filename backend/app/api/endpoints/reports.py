"""API router for citizen flood reports, crowdsourced verification, and tracking."""
from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.auth import verify_operator_access
from app.database.models import (
    CitizenReportCreate,
    CitizenReportResponse,
    VerificationActionRequest,
)
from app.services.citizen_service import citizen_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["citizen_reports"])


@router.post("", response_model=CitizenReportResponse, status_code=status.HTTP_201_CREATED)
async def submit_citizen_report(request: Request) -> CitizenReportResponse:
    """Submits a citizen flood report or clear-pass control report.

    Supports both multipart/form-data (with optional photo upload) and application/json.
    """
    ct = request.headers.get("content-type", "").lower()

    try:
        if "application/json" in ct:
            body = await request.json()
            report_data = CitizenReportCreate(**body)
            return citizen_service.create_report(report_data)

        elif "multipart/form-data" in ct or "application/x-www-form-urlencoded" in ct:
            form = await request.form()
            image_file = form.get("image")
            image_bytes: bytes | None = None
            image_filename: str | None = None

            if image_file and hasattr(image_file, "read"):
                image_bytes = await image_file.read()
                image_filename = getattr(image_file, "filename", "report.jpg")

            depth_val = form.get("water_depth_cm")
            depth = float(depth_val) if depth_val not in (None, "") else None

            sev_val = form.get("severity")
            sev = int(sev_val) if sev_val not in (None, "") else None

            lat_val = form.get("latitude")
            lat = float(lat_val) if lat_val not in (None, "") else None

            lng_val = form.get("longitude")
            lng = float(lng_val) if lng_val not in (None, "") else None

            report_data = CitizenReportCreate(
                spot_id=str(form.get("spot_id")).strip() if form.get("spot_id") else None,
                report_type=str(form.get("report_type", "flood")).strip(),
                water_depth_cm=depth,
                severity=sev,
                severity_level=str(form.get("severity_level")).strip() if form.get("severity_level") else None,
                latitude=lat,
                longitude=lng,
                reporter_alias=str(form.get("reporter_alias")).strip() if form.get("reporter_alias") else "Anonymous Citizen",
                notes=str(form.get("notes")).strip() if form.get("notes") else None,
            )
            return citizen_service.create_report(
                report_data, image_bytes=image_bytes, image_filename=image_filename
            )

        else:
            # Fallback attempt to read json or empty form
            body = await request.json()
            report_data = CitizenReportCreate(**body)
            return citizen_service.create_report(report_data)

    except ValueError as e:
        logger.warning(f"Validation error creating citizen report: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating citizen report: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit citizen report: {e}",
        )


@router.get("", response_model=list[CitizenReportResponse])
def list_citizen_reports(
    spot_id: str | None = Query(default=None, description="Filter by spot ID"),
    status: str | None = Query(default=None, description="Filter by verification status"),
    limit: int = Query(default=50, ge=1, le=200, description="Max reports to return"),
) -> list[CitizenReportResponse]:
    """Retrieves recent citizen flood and control reports."""
    return citizen_service.list_reports(spot_id=spot_id, status=status, limit=limit)


@router.get("/{report_id}", response_model=CitizenReportResponse)
def get_citizen_report(report_id: str) -> CitizenReportResponse:
    """Retrieves status and details for an individual report by tracking token/id."""
    report = citizen_service.get_report(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with tracking ID '{report_id}' was not found.",
        )
    return report


@router.post(
    "/{report_id}/verify",
    response_model=CitizenReportResponse,
    dependencies=[Depends(verify_operator_access)],
)
def verify_citizen_report(
    report_id: str, action_req: VerificationActionRequest
) -> CitizenReportResponse:
    """Updates verification status for a citizen report (guarded municipal review action)."""
    try:
        updated = citizen_service.update_verification(
            report_id=report_id,
            action=action_req.action,
            operator_id=action_req.operator_id,
            notes=action_req.notes,
            reason=action_req.reason,
            duplicate_of_id=action_req.duplicate_of_id,
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report '{report_id}' not found.",
            )
        return updated
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

