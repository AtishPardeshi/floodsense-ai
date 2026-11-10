"""API endpoints for Civic Response Coordination and In-App Notifications."""
from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status

from app.core.auth import verify_operator_access
from app.database.models import (
    InAppNotificationResponse,
    PublicAlertApprovalRequest,
    ResponseTaskCreate,
    ResponseTaskResponse,
    TaskAssignRequest,
    TaskNoteCreate,
    TaskNoteResponse,
    TaskPriorityBreakdown,
    TaskStatusUpdateRequest,
)
from app.services.coordination_service import coordination_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/coordination",
    tags=["response_coordination"],
)


# --------------------------------------------------------------------------
# Task Management Endpoints
# --------------------------------------------------------------------------


@router.post(
    "/tasks",
    response_model=ResponseTaskResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_operator_access)],
)
def create_response_task(
    task_data: ResponseTaskCreate,
) -> ResponseTaskResponse:
    """Creates a new civic response task from verified flood intelligence.

    Requires valid operator credentials (X-Operator-Key).
    """
    try:
        return coordination_service.create_task(task_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create response task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create response task: {e}",
        )


@router.get("/tasks", response_model=list[ResponseTaskResponse])
def list_response_tasks(
    status: str | None = Query(default=None, description="Filter by task status"),
    responder_id: str | None = Query(default=None, description="Filter by assigned responder unit"),
    spot_id: str | None = Query(default=None, description="Filter by monitored spot ID"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ResponseTaskResponse]:
    """Retrieves civic response tasks ordered by priority and recency."""
    return coordination_service.list_tasks(
        status=status,
        responder_id=responder_id,
        spot_id=spot_id,
        limit=limit,
    )


@router.get("/tasks/priority-preview", response_model=TaskPriorityBreakdown)
def preview_task_priority(
    spot_id: str = Query(..., description="Target monitored spot ID"),
    incident_report_id: str | None = Query(default=None, description="Optional associated report ID"),
    override_severity: int | None = Query(default=None, ge=1, le=4),
) -> TaskPriorityBreakdown:
    """Pre-computes deterministic prioritization score factors before task creation."""
    try:
        return coordination_service.calculate_task_priority(
            spot_id=spot_id,
            incident_report_id=incident_report_id,
            override_severity=override_severity,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/tasks/{task_id}", response_model=ResponseTaskResponse)
def get_response_task(task_id: str) -> ResponseTaskResponse:
    """Fetches full task details including progress notes and priority scoring breakdown."""
    task = coordination_service.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Response task '{task_id}' not found.",
        )
    return task


@router.post(
    "/tasks/{task_id}/assign",
    response_model=ResponseTaskResponse,
    dependencies=[Depends(verify_operator_access)],
)
def assign_response_task(
    task_id: str,
    assign_req: TaskAssignRequest,
) -> ResponseTaskResponse:
    """Assigns or dispatches an open task to a specific field responder unit.

    Requires municipal operator authorization (X-Operator-Key).
    """
    try:
        return coordination_service.assign_task(
            task_id=task_id,
            responder_id=assign_req.responder_id,
            operator_id=assign_req.operator_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to assign task {task_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign response task: {e}",
        )


@router.patch("/tasks/{task_id}/status", response_model=ResponseTaskResponse)
def update_task_status(
    task_id: str,
    update_req: TaskStatusUpdateRequest,
    x_responder_id: str | None = Header(default=None, alias="X-Responder-Id"),
) -> ResponseTaskResponse:
    """Updates operational state of a task (e.g. assigned -> in_progress -> resolved).

    Enforces that responders can only progress tasks assigned to their unit.
    """
    actor_id = x_responder_id or update_req.actor_id
    try:
        return coordination_service.update_task_status(
            task_id=task_id,
            new_status=update_req.status,
            actor_id=actor_id,
            actor_role=update_req.actor_role,
            notes=update_req.notes,
        )
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update task {task_id} status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Status update failed: {e}",
        )


@router.post("/tasks/{task_id}/resolve", response_model=ResponseTaskResponse)
async def resolve_task_with_evidence(
    task_id: str,
    notes: str = Form(..., description="Action taken and water clearance notes"),
    actor_id: str = Form(..., description="Responder or Operator ID"),
    actor_role: str = Form("responder", description="Role of the actor"),
    file: UploadFile | None = File(default=None, description="Resolution photo verification"),
    x_responder_id: str | None = Header(default=None, alias="X-Responder-Id"),
) -> ResponseTaskResponse:
    """Marks a task as resolved with mandatory completion notes and optional photographic proof."""
    effective_actor_id = x_responder_id or actor_id
    image_bytes: bytes | None = None
    image_filename: str | None = None

    if file:
        image_bytes = await file.read()
        image_filename = file.filename

    try:
        return coordination_service.update_task_status(
            task_id=task_id,
            new_status="resolved",
            actor_id=effective_actor_id,
            actor_role=actor_role,
            notes=notes,
            resolution_image_bytes=image_bytes,
            resolution_image_filename=image_filename,
        )
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to resolve task {task_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Task resolution failed: {e}",
        )


@router.post("/tasks/{task_id}/notes", response_model=TaskNoteResponse)
def add_task_note(
    task_id: str,
    note_req: TaskNoteCreate,
    x_responder_id: str | None = Header(default=None, alias="X-Responder-Id"),
) -> TaskNoteResponse:
    """Appends an operational field progress note to a response task."""
    actor_id = x_responder_id or note_req.author_id
    try:
        return coordination_service.add_progress_note(
            task_id=task_id,
            note_text=note_req.note,
            author_id=actor_id,
            author_role=note_req.author_role,
        )
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to append note to task {task_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add note: {e}",
        )


# --------------------------------------------------------------------------
# Local In-App Notification Centre Endpoints
# --------------------------------------------------------------------------


@router.get("/notifications", response_model=list[InAppNotificationResponse])
def list_in_app_notifications(
    target_audience: str | None = Query(default=None, description="Filter by audience (operator, responder, public_advisory)"),
    responder_id: str | None = Query(default=None, description="Filter by responder unit"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[InAppNotificationResponse]:
    """Retrieves in-app notifications generated from verified actions and task lifecycle events."""
    return coordination_service.list_notifications(
        target_audience=target_audience,
        responder_id=responder_id,
        limit=limit,
    )


@router.post(
    "/notifications/{notification_id}/approve",
    response_model=InAppNotificationResponse,
    dependencies=[Depends(verify_operator_access)],
)
def approve_public_emergency_alert(
    notification_id: str,
    approval_req: PublicAlertApprovalRequest = PublicAlertApprovalRequest(),
) -> InAppNotificationResponse:
    """Human operator approval gate for public/emergency alerts before delivery.

    Strictly requires operator authorization (X-Operator-Key).
    """
    try:
        return coordination_service.approve_public_alert(
            notification_id=notification_id,
            operator_id=approval_req.operator_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to approve notification {notification_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve notification: {e}",
        )

