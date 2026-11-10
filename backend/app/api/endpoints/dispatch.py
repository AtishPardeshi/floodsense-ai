"""API endpoints for municipal dewatering pump and barricade dispatch management."""
from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import verify_operator_access
from app.database.models import (
    MunicipalDispatchCreate,
    MunicipalDispatchResponse,
    MunicipalDispatchStatusUpdate,
)
from app.services.dispatch_service import dispatch_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/dispatch",
    tags=["municipal_dispatch"],
    dependencies=[Depends(verify_operator_access)],  # Protected operator actions
)


@router.post("/orders", response_model=MunicipalDispatchResponse, status_code=status.HTTP_201_CREATED)
def create_dispatch_order(
    dispatch_req: MunicipalDispatchCreate,
) -> MunicipalDispatchResponse:
    """Issues a municipal directive: dewatering pump deployment, barricade order, or traffic diversion."""
    try:
        return dispatch_service.create_dispatch(dispatch_req)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create dispatch order: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/orders", response_model=list[MunicipalDispatchResponse])
def list_dispatch_orders(
    status: str | None = Query(default=None, description="Filter by operational status"),
    spot_id: str | None = Query(default=None, description="Filter by spot ID"),
) -> list[MunicipalDispatchResponse]:
    """Retrieves all active and historical municipal dispatches."""
    return dispatch_service.list_dispatches(status=status, spot_id=spot_id)


@router.patch("/orders/{dispatch_id}/status", response_model=MunicipalDispatchResponse)
def update_dispatch_order_status(
    dispatch_id: str,
    update_req: MunicipalDispatchStatusUpdate,
) -> MunicipalDispatchResponse:
    """Updates operational state of a municipal dispatch (ordered -> en_route -> active -> demobilized)."""
    try:
        return dispatch_service.update_dispatch_status(
            dispatch_id=dispatch_id,
            status=update_req.status,
            operator_id=update_req.operator_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

