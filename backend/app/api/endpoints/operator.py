"""API endpoints for municipal operator verification dashboard and triage queue."""
from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import verify_operator_access
from app.database.models import (
    CitizenReportResponse,
    OperatorDecisionRequest,
    OperatorReportItem,
)
from app.services.operator_service import operator_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/operator",
    tags=["operator_verification"],
    dependencies=[Depends(verify_operator_access)],  # Strict authentication guard
)


@router.get("/queue", response_model=list[OperatorReportItem])
def get_operator_queue(
    status: str | None = Query(default=None, description="Filter queue by status"),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[OperatorReportItem]:
    """Retrieves operator review queue enriched with duplicate detection alerts."""
    return operator_service.list_operator_queue(status=status, limit=limit)


@router.post("/reports/{report_id}/decision", response_model=CitizenReportResponse)
def execute_operator_decision(
    report_id: str,
    decision_req: OperatorDecisionRequest,
) -> CitizenReportResponse:
    """Executes municipal operator decision (approve, reject, needs_info) with audit logging."""
    try:
        updated = operator_service.execute_decision(
            report_id=report_id,
            decision=decision_req.decision,
            reviewer_id=decision_req.reviewer_id,
            reason=decision_req.reason,
            duplicate_of_id=decision_req.duplicate_of_id,
        )
        return updated
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error executing operator decision for {report_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record operator decision: {e}",
        )


@router.post("/reports/{report_id}/link-duplicate", response_model=CitizenReportResponse)
def link_duplicate_report(
    report_id: str,
    parent_report_id: str = Query(..., description="ID of the primary report to link to"),
    reason: str | None = Query(default=None, description="Reason for duplicate linking"),
    reviewer_id: str = Query(default="BBMP_Control_Operator", description="Operator identity"),
) -> CitizenReportResponse:
    """Links report as a duplicate of an existing primary report and marks it excluded from active evidence."""
    try:
        updated = operator_service.link_duplicate(
            report_id=report_id,
            parent_report_id=parent_report_id,
            reviewer_id=reviewer_id,
            reason=reason,
        )
        return updated
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

