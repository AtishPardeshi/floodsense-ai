"""Pydantic data models for Citizen Intelligence and Municipal Response Coordination."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

ReportType = Literal["flood", "control_clear"]
SeverityLevel = Literal["low", "medium", "high", "critical"]
VerificationStatus = Literal[
    "submitted", "pending", "under_review", "approved", "verified", "rejected", "needs_info"
]
DirectiveType = Literal["pump_deployment", "barricade_order", "traffic_diversion"]
DispatchPriority = Literal["P1_CRITICAL", "P2_ELEVATED", "P3_ROUTINE"]
DispatchStatus = Literal["ordered", "en_route", "active", "demobilized"]


class CitizenReportCreate(BaseModel):
    spot_id: str | None = None
    report_type: ReportType = "flood"
    water_depth_cm: float | None = Field(default=None, ge=0, le=300)
    severity: int | None = Field(default=None, ge=1, le=4)
    severity_level: SeverityLevel | None = "medium"
    latitude: float | None = None
    longitude: float | None = None
    reporter_alias: str | None = "Anonymous Citizen"
    notes: str | None = None


class CitizenReportResponse(BaseModel):
    report_id: str
    spot_id: str
    spot_name: str | None = None
    report_type: ReportType
    water_depth_cm: float | None = None
    severity: int | None = None
    severity_level: SeverityLevel | None = "medium"
    latitude: float
    longitude: float
    image_url: str | None = None
    reporter_alias: str = "Anonymous Citizen"
    verification_status: str = "submitted"
    verified_at: str | None = None
    verified_by: str | None = None
    notes: str | None = None
    duplicate_of_id: str | None = None
    decision_reason: str | None = None
    created_at: str


class VerificationActionRequest(BaseModel):
    action: Literal["approve", "approved", "verify", "verified", "under_review", "reject", "rejected", "needs_info"]
    operator_id: str = "BBMP_Control_Cell"
    notes: str | None = None
    reason: str | None = None
    duplicate_of_id: str | None = None


class OperatorDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected", "needs_info", "under_review"]
    reviewer_id: str = "BBMP_Control_Operator"
    reason: str | None = None
    duplicate_of_id: str | None = None


class OperatorReportItem(CitizenReportResponse):
    nearby_reports_count: int = 0
    potential_duplicate_of: str | None = None
    duplicate_warning: str | None = None


EvidenceStatus = Literal["none", "watch", "elevated", "critical"]
EvidenceConfidence = Literal["none", "low", "medium", "high"]
EvidenceFreshness = Literal["none", "fresh", "recent", "decayed", "expired"]


class OperationalEvidenceResponse(BaseModel):
    spot_id: str
    spot_name: str
    approved_reports_nearby: int
    pending_reports_nearby: int
    latest_verified_at: str | None = None
    evidence_status: EvidenceStatus
    confidence: EvidenceConfidence
    freshness: EvidenceFreshness
    source: str = "human_verified_citizen_reports"
    radius_meters: float
    window_hours: float
    explanation: str
    approved_report_ids: list[str] = Field(default_factory=list)
    pending_report_ids: list[str] = Field(default_factory=list)


class MunicipalDispatchCreate(BaseModel):
    spot_id: str
    report_id: str | None = None
    directive_type: DirectiveType = "pump_deployment"
    priority: DispatchPriority = "P1_CRITICAL"
    capacity_gpm: str | None = "500 GPM"
    assigned_team: str | None = "BBMP Stormwater Rapid Response"
    action_instructions: str


class MunicipalDispatchResponse(BaseModel):
    dispatch_id: str
    spot_id: str
    location_name: str
    report_id: str | None = None
    directive_type: DirectiveType
    priority: DispatchPriority
    status: DispatchStatus
    capacity_gpm: str | None = None
    assigned_team: str | None = None
    action_instructions: str
    created_at: str
    updated_at: str


class MunicipalDispatchStatusUpdate(BaseModel):
    status: DispatchStatus
    operator_id: str = "BBMP_Control_Cell"
    notes: str | None = None


# --------------------------------------------------------------------------
# Response Coordination Tasks & Notification Centre Models
# --------------------------------------------------------------------------

TaskStatus = Literal["open", "assigned", "in_progress", "resolved", "cancelled"]
TaskPriority = Literal["P1_CRITICAL", "P2_HIGH", "P3_MEDIUM", "P4_LOW"]


class TaskPriorityFactor(BaseModel):
    factor: str
    points: int
    reason: str


class TaskPriorityBreakdown(BaseModel):
    calculated_priority: TaskPriority
    total_score: int
    factors: list[TaskPriorityFactor]
    explanation: str


class TaskNoteResponse(BaseModel):
    note_id: int
    task_id: str
    author_id: str
    author_role: str
    note: str
    created_at: str


class ResponseTaskCreate(BaseModel):
    incident_report_id: str | None = None
    spot_id: str
    title: str
    description: str
    assigned_responder_id: str | None = None
    priority: TaskPriority | None = None
    due_at: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class ResponseTaskUpdate(BaseModel):
    status: TaskStatus | None = None
    assigned_responder_id: str | None = None
    progress_note: str | None = None
    resolution_notes: str | None = None


class TaskAssignRequest(BaseModel):
    responder_id: str
    operator_id: str = "BBMP_Control_Operator"


class TaskStatusUpdateRequest(BaseModel):
    status: TaskStatus
    actor_id: str
    actor_role: str = "responder"
    notes: str | None = None


class TaskNoteCreate(BaseModel):
    note: str
    author_id: str
    author_role: str = "responder"


class PublicAlertApprovalRequest(BaseModel):
    operator_id: str = "BBMP_Chief_Duty_Officer"



class ResponseTaskResponse(BaseModel):
    task_id: str
    incident_report_id: str | None = None
    spot_id: str
    location_name: str
    latitude: float
    longitude: float
    title: str
    description: str
    priority: TaskPriority
    priority_reasons: TaskPriorityBreakdown | None = None
    assigned_responder_id: str | None = None
    assigned_by: str | None = None
    status: TaskStatus
    due_at: str | None = None
    resolution_notes: str | None = None
    resolution_image_url: str | None = None
    resolved_at: str | None = None
    notes: list[TaskNoteResponse] = Field(default_factory=list)
    created_at: str
    updated_at: str


NotificationAudience = Literal["operator", "responder", "public_advisory"]
NotificationSeverity = Literal["info", "warning", "critical"]
NotificationDeliveryStatus = Literal[
    "logged_locally", "delivered_in_app", "acknowledged", "pending_approval"
]


class InAppNotificationResponse(BaseModel):
    notification_id: str
    task_id: str | None = None
    report_id: str | None = None
    target_audience: NotificationAudience
    target_responder_id: str | None = None
    title: str
    message: str
    severity: NotificationSeverity
    delivery_status: NotificationDeliveryStatus
    requires_human_approval: bool = False
    approved_by: str | None = None
    approved_at: str | None = None
    created_at: str
