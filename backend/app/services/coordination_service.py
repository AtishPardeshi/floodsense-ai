"""Civic Response Coordination & Task Management Service for FloodSense AI.

Translates human-verified flood intelligence into actionable field response tasks,
computes deterministic transparent prioritisation, manages responder workflows,
and powers the local in-app notification centre.

CRITICAL INTEGRITY RULES:
- Deterministic prioritization uses ONLY verified incident severity, approved nearby reports,
  evidence freshness, and authoritative physical spot depression data.
- Does NOT invent population, traffic, or damage statistics.
- Responders can only modify tasks explicitly assigned to them.
- Public/emergency alerts strictly require human operator approval.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from pathlib import Path

from app.database.db import get_db
from app.database.models import (
    InAppNotificationResponse,
    NotificationAudience,
    NotificationDeliveryStatus,
    NotificationSeverity,
    ResponseTaskCreate,
    ResponseTaskResponse,
    ResponseTaskUpdate,
    TaskNoteResponse,
    TaskPriority,
    TaskPriorityBreakdown,
    TaskPriorityFactor,
    TaskStatus,
)
from app.demo.fixtures import SPOTS
from app.services.citizen_service import citizen_service
from app.services.evidence_service import evidence_service

SPOTS_BY_ID = {s.id: s for s in SPOTS}

# Allowed status transitions graph
ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    "open": {"assigned", "cancelled"},
    "assigned": {"in_progress", "assigned", "cancelled"},
    "in_progress": {"resolved", "cancelled"},
    "resolved": set(),
    "cancelled": set(),
}


class CoordinationService:
    """Manages response tasks, deterministic prioritization, and in-app notifications."""

    # --------------------------------------------------------------------------
    # 1. Deterministic Prioritization Service
    # --------------------------------------------------------------------------
    def calculate_task_priority(
        self,
        spot_id: str,
        incident_report_id: str | None = None,
        override_severity: int | None = None,
    ) -> TaskPriorityBreakdown:
        """Computes deterministic priority using verified severity, nearby evidence, freshness, and terrain exposure."""
        spot = SPOTS_BY_ID.get(spot_id)
        if not spot:
            raise ValueError(f"Spot '{spot_id}' is not a registered monitored location.")

        factors: list[TaskPriorityFactor] = []
        total_score = 0

        # Factor 1: Verified Incident Severity
        sev = override_severity
        depth_cm: float | None = None
        if incident_report_id:
            rep = citizen_service.get_report(incident_report_id)
            if rep:
                sev = rep.severity or sev
                depth_cm = rep.water_depth_cm

        if sev == 4 or (depth_cm and depth_cm >= 80.0):
            pts = 40
            reason = f"Critical severity waterlogging ({depth_cm or '>80'} cm submerged roadway)"
        elif sev == 3 or (depth_cm and depth_cm >= 45.0):
            pts = 30
            reason = f"High severity waterlogging ({depth_cm or '45-80'} cm observed depth)"
        elif sev == 2 or (depth_cm and depth_cm >= 15.0):
            pts = 20
            reason = f"Medium severity waterlogging ({depth_cm or '15-45'} cm observed depth)"
        elif sev == 1:
            pts = 10
            reason = "Low severity water accumulation (<15 cm)"
        else:
            pts = 15
            reason = "Standard baseline severity (unspecified depth)"

        factors.append(TaskPriorityFactor(factor="incident_severity", points=pts, reason=reason))
        total_score += pts

        # Factor 2: Number of Approved Nearby Reports (evidence corroboration)
        ev = evidence_service.get_spot_evidence(spot_id=spot_id, radius_meters=1500, window_hours=6)
        n_approved = ev.approved_reports_nearby

        if n_approved >= 3:
            pts = 25
            reason = f"{n_approved} human-verified citizen reports in proximity (widespread corroboration)"
        elif n_approved == 2:
            pts = 15
            reason = "2 human-verified citizen reports in proximity"
        elif n_approved == 1:
            pts = 10
            reason = "1 human-verified citizen report in proximity"
        else:
            pts = 0
            reason = "0 nearby verified reports (single incident report)"

        factors.append(TaskPriorityFactor(factor="nearby_corroboration", points=pts, reason=reason))
        total_score += pts

        # Factor 3: Evidence Freshness
        freshness = ev.freshness
        if freshness == "fresh":
            pts = 20
            reason = "Fresh verified evidence filed within past 2 hours (active storm threat)"
        elif freshness == "recent":
            pts = 10
            reason = "Recent verified evidence filed within past 6 hours"
        elif freshness == "decayed":
            pts = 5
            reason = "Decayed evidence (6 to 24 hours old)"
        else:
            pts = 0
            reason = "No active fresh evidence in window"

        factors.append(TaskPriorityFactor(factor="evidence_freshness", points=pts, reason=reason))
        total_score += pts

        # Factor 4: Location Exposure or Criticality (from verified physical terrain baseline)
        if spot.rel_depth_m >= 3.5:
            pts = 15
            reason = (
                f"Critical underpass depression ({spot.name}, rel_depth={spot.rel_depth_m}m, "
                f"catchment={spot.catchment_ha}ha)"
            )
        elif spot.rel_depth_m >= 2.0:
            pts = 10
            reason = f"Moderate carriageway depression ({spot.name}, rel_depth={spot.rel_depth_m}m)"
        else:
            pts = 5
            reason = f"Standard surface gradient ({spot.name}, rel_depth={spot.rel_depth_m}m)"

        factors.append(TaskPriorityFactor(factor="location_criticality", points=pts, reason=reason))
        total_score += pts

        # Determine Priority Band
        if total_score >= 70:
            priority: TaskPriority = "P1_CRITICAL"
        elif total_score >= 50:
            priority = "P2_HIGH"
        elif total_score >= 30:
            priority = "P3_MEDIUM"
        else:
            priority = "P4_LOW"

        explanation = (
            f"{priority} assigned with score {total_score}/100 based on: "
            + "; ".join(f"{f.points}pts for {f.factor}" for f in factors)
            + "."
        )

        return TaskPriorityBreakdown(
            calculated_priority=priority,
            total_score=total_score,
            factors=factors,
            explanation=explanation,
        )

    # --------------------------------------------------------------------------
    # 2. Task Creation & Assignment
    # --------------------------------------------------------------------------
    def create_task(
        self,
        task_data: ResponseTaskCreate,
        operator_id: str = "BBMP_Control_Operator",
    ) -> ResponseTaskResponse:
        """Creates a response coordination task from verified evidence or spot monitoring."""
        spot = SPOTS_BY_ID.get(task_data.spot_id)
        if not spot:
            raise ValueError(f"Spot '{task_data.spot_id}' is not a registered monitored location.")

        lat = task_data.latitude if task_data.latitude is not None else spot.lat
        lng = task_data.longitude if task_data.longitude is not None else spot.lng

        # Compute priority breakdown if not manually specified
        priority_breakdown = self.calculate_task_priority(
            spot_id=task_data.spot_id,
            incident_report_id=task_data.incident_report_id,
        )
        final_priority = task_data.priority or priority_breakdown.calculated_priority

        task_id = f"task_{uuid.uuid4().hex[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        initial_status: TaskStatus = "assigned" if task_data.assigned_responder_id else "open"

        # Default due time to 2 hours for critical/high, 4 hours for medium/low
        due_at = task_data.due_at
        if not due_at:
            hours_due = 2 if final_priority in ("P1_CRITICAL", "P2_HIGH") else 4
            due_at = (datetime.now(timezone.utc) + timedelta(hours=hours_due)).isoformat(timespec="seconds")

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO response_tasks (
                    task_id, incident_report_id, spot_id, location_name, latitude, longitude,
                    title, description, priority, priority_reasons_json, assigned_responder_id,
                    assigned_by, status, due_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    task_data.incident_report_id,
                    task_data.spot_id,
                    spot.name,
                    lat,
                    lng,
                    task_data.title,
                    task_data.description,
                    final_priority,
                    json.dumps(priority_breakdown.model_dump()),
                    task_data.assigned_responder_id,
                    operator_id if task_data.assigned_responder_id else None,
                    initial_status,
                    due_at,
                    now_iso,
                    now_iso,
                ),
            )

            # Audit log
            cursor.execute(
                """
                INSERT INTO response_audit_log (event_timestamp, action, actor_role, details_json)
                VALUES (?, 'response_task_created', 'municipal_operator', ?)
                """,
                (
                    now_iso,
                    json.dumps(
                        {
                            "task_id": task_id,
                            "spot_id": task_data.spot_id,
                            "priority": final_priority,
                            "assigned_to": task_data.assigned_responder_id,
                            "operator_id": operator_id,
                        }
                    ),
                ),
            )

        # Generate in-app notifications
        if task_data.assigned_responder_id:
            self.create_notification(
                title=f"New Task Assigned ({final_priority})",
                message=f"You have been assigned to {task_data.title} at {spot.name}.",
                severity="critical" if final_priority == "P1_CRITICAL" else "warning",
                target_audience="responder",
                target_responder_id=task_data.assigned_responder_id,
                task_id=task_id,
                delivery_status="delivered_in_app",
            )

        self.create_notification(
            title=f"Response Task Logged: {task_data.title}",
            message=f"Task {task_id} registered for {spot.name} [{final_priority}].",
            severity="info",
            target_audience="operator",
            task_id=task_id,
            delivery_status="logged_locally",
        )

        return self.get_task(task_id)  # type: ignore

    def assign_task(
        self,
        task_id: str,
        responder_id: str,
        operator_id: str = "BBMP_Control_Operator",
    ) -> ResponseTaskResponse:
        """Assigns or re-assigns an existing task to a field responder (operator permission required)."""
        current = self.get_task(task_id)
        if not current:
            raise KeyError(f"Task '{task_id}' not found.")

        if current.status in ("resolved", "cancelled"):
            raise ValueError(f"Cannot assign task in terminal state '{current.status}'.")

        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        new_status = "assigned" if current.status == "open" else current.status

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE response_tasks
                SET assigned_responder_id = ?, assigned_by = ?, status = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (responder_id, operator_id, new_status, now_iso, task_id),
            )
            cursor.execute(
                """
                INSERT INTO response_audit_log (event_timestamp, action, actor_role, details_json)
                VALUES (?, 'response_task_assigned', 'municipal_operator', ?)
                """,
                (
                    now_iso,
                    json.dumps(
                        {"task_id": task_id, "responder_id": responder_id, "operator_id": operator_id}
                    ),
                ),
            )

        self.create_notification(
            title="Task Assigned to Your Unit",
            message=f"Task {task_id} ({current.title}) assigned to you by {operator_id}.",
            severity="warning" if current.priority in ("P1_CRITICAL", "P2_HIGH") else "info",
            target_audience="responder",
            target_responder_id=responder_id,
            task_id=task_id,
            delivery_status="delivered_in_app",
        )

        return self.get_task(task_id)  # type: ignore

    # --------------------------------------------------------------------------
    # 3. Status Transitions & Responder Workflow
    # --------------------------------------------------------------------------
    def update_task_status(
        self,
        task_id: str,
        new_status: TaskStatus,
        actor_id: str,
        actor_role: str = "responder",
        notes: str | None = None,
        resolution_image_bytes: bytes | None = None,
        resolution_image_filename: str | None = None,
    ) -> ResponseTaskResponse:
        """Updates task status with strict transition validation and responder authorization."""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        # Access control: Responders may only update tasks assigned to them
        if actor_role == "responder":
            if not task.assigned_responder_id or task.assigned_responder_id != actor_id:
                raise PermissionError(
                    f"Access Denied: Responder '{actor_id}' is not assigned to task '{task_id}'."
                )

        # Transition validation
        allowed = ALLOWED_TRANSITIONS.get(task.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid status transition: Cannot transition from '{task.status}' to '{new_status}'. "
                f"Permitted next states: {list(allowed) or 'None (terminal state)'}."
            )

        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        saved_img_name: str | None = None

        if resolution_image_bytes and resolution_image_filename:
            saved_img_name = citizen_service.save_image(resolution_image_bytes, resolution_image_filename)

        with get_db() as conn:
            cursor = conn.cursor()
            resolved_at = now_iso if new_status == "resolved" else task.resolved_at
            cursor.execute(
                """
                UPDATE response_tasks
                SET status = ?, updated_at = ?,
                    resolved_at = COALESCE(?, resolved_at),
                    resolution_notes = COALESCE(?, resolution_notes),
                    resolution_image_filename = COALESCE(?, resolution_image_filename)
                WHERE task_id = ?
                """,
                (new_status, now_iso, resolved_at, notes, saved_img_name, task_id),
            )

            # Add progress note if text provided
            if notes:
                cursor.execute(
                    """
                    INSERT INTO task_progress_notes (task_id, author_id, author_role, note, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (task_id, actor_id, actor_role, notes, now_iso),
                )

            # Audit log
            audit_actor_role = "municipal_operator" if actor_role in ("responder", "operator", "municipal_operator") else "system_agent"
            cursor.execute(
                """
                INSERT INTO response_audit_log (event_timestamp, action, actor_role, details_json)
                VALUES (?, 'response_task_status_updated', ?, ?)
                """,
                (
                    now_iso,
                    audit_actor_role,
                    json.dumps(
                        {
                            "task_id": task_id,
                            "old_status": task.status,
                            "new_status": new_status,
                            "actor_id": actor_id,
                            "actor_role": actor_role,
                            "has_image": bool(saved_img_name),
                        }
                    ),
                ),
            )

        # Notification for operator upon status progression or resolution
        self.create_notification(
            title=f"Task {new_status.replace('_', ' ').title()}: {task.title}",
            message=f"Unit {actor_id} transitioned task {task_id} to '{new_status}'.",
            severity="info" if new_status != "resolved" else "warning",
            target_audience="operator",
            task_id=task_id,
            delivery_status="logged_locally",
        )

        return self.get_task(task_id)  # type: ignore

    def add_progress_note(
        self,
        task_id: str,
        note_text: str,
        author_id: str,
        author_role: str = "responder",
    ) -> TaskNoteResponse:
        """Adds a progress update note to an existing task."""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        if author_role == "responder":
            if not task.assigned_responder_id or task.assigned_responder_id != author_id:
                raise PermissionError(
                    f"Access Denied: Responder '{author_id}' is not assigned to task '{task_id}'."
                )

        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO task_progress_notes (task_id, author_id, author_role, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, author_id, author_role, note_text, now_iso),
            )
            note_id = cursor.lastrowid

            cursor.execute(
                """
                UPDATE response_tasks SET updated_at = ? WHERE task_id = ?
                """,
                (now_iso, task_id),
            )

            audit_actor_role = "municipal_operator" if author_role in ("responder", "operator", "municipal_operator") else "system_agent"
            cursor.execute(
                """
                INSERT INTO response_audit_log (event_timestamp, action, actor_role, details_json)
                VALUES (?, 'task_progress_note_added', ?, ?)
                """,
                (now_iso, audit_actor_role, json.dumps({"task_id": task_id, "note_id": note_id, "author": author_id, "role": author_role})),
            )

        return TaskNoteResponse(
            note_id=note_id,  # type: ignore
            task_id=task_id,
            author_id=author_id,
            author_role=author_role,
            note=note_text,
            created_at=now_iso,
        )

    # --------------------------------------------------------------------------
    # 4. Queries
    # --------------------------------------------------------------------------
    def get_task(self, task_id: str) -> ResponseTaskResponse | None:
        """Retrieves an individual response task with notes and priority breakdown."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM response_tasks WHERE task_id = ?", (task_id,))
            r = cursor.fetchone()
            if not r:
                return None

            cursor.execute(
                "SELECT * FROM task_progress_notes WHERE task_id = ? ORDER BY created_at ASC",
                (task_id,),
            )
            notes_rows = cursor.fetchall()
            notes = [
                TaskNoteResponse(
                    note_id=n["note_id"],
                    task_id=n["task_id"],
                    author_id=n["author_id"],
                    author_role=n["author_role"],
                    note=n["note"],
                    created_at=n["created_at"],
                )
                for n in notes_rows
            ]

        priority_breakdown: TaskPriorityBreakdown | None = None
        if r["priority_reasons_json"]:
            try:
                priority_breakdown = TaskPriorityBreakdown(**json.loads(r["priority_reasons_json"]))
            except Exception:
                pass

        img_url = f"/static/uploads/{r['resolution_image_filename']}" if r["resolution_image_filename"] else None

        return ResponseTaskResponse(
            task_id=r["task_id"],
            incident_report_id=r["incident_report_id"],
            spot_id=r["spot_id"],
            location_name=r["location_name"],
            latitude=r["latitude"],
            longitude=r["longitude"],
            title=r["title"],
            description=r["description"],
            priority=r["priority"],
            priority_reasons=priority_breakdown,
            assigned_responder_id=r["assigned_responder_id"],
            assigned_by=r["assigned_by"],
            status=r["status"],
            due_at=r["due_at"],
            resolution_notes=r["resolution_notes"],
            resolution_image_url=img_url,
            resolved_at=r["resolved_at"],
            notes=notes,
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def list_tasks(
        self,
        status: str | None = None,
        responder_id: str | None = None,
        spot_id: str | None = None,
        limit: int = 50,
    ) -> list[ResponseTaskResponse]:
        """Lists response tasks with optional filters."""
        query = "SELECT task_id FROM response_tasks WHERE 1=1"
        params: list[Any] = []

        if status and status != "all":
            query += " AND status = ?"
            params.append(status)

        if responder_id:
            query += " AND assigned_responder_id = ?"
            params.append(responder_id)

        if spot_id:
            query += " AND spot_id = ?"
            params.append(spot_id)

        query += " ORDER BY CASE priority WHEN 'P1_CRITICAL' THEN 1 WHEN 'P2_HIGH' THEN 2 WHEN 'P3_MEDIUM' THEN 3 ELSE 4 END, created_at DESC LIMIT ?"
        params.append(limit)

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            task_ids = [row["task_id"] for row in cursor.fetchall()]

        return [self.get_task(tid) for tid in task_ids if tid]  # type: ignore

    # --------------------------------------------------------------------------
    # 5. Local In-App Notification Centre
    # --------------------------------------------------------------------------
    def create_notification(
        self,
        title: str,
        message: str,
        severity: NotificationSeverity = "info",
        target_audience: NotificationAudience = "operator",
        target_responder_id: str | None = None,
        task_id: str | None = None,
        report_id: str | None = None,
        requires_human_approval: bool = False,
        delivery_status: NotificationDeliveryStatus = "logged_locally",
    ) -> InAppNotificationResponse:
        """Records an in-app notification without claiming external delivery."""
        notif_id = f"notif_{uuid.uuid4().hex[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO in_app_notifications (
                    notification_id, task_id, report_id, target_audience,
                    target_responder_id, title, message, severity,
                    delivery_status, requires_human_approval, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    notif_id,
                    task_id,
                    report_id,
                    target_audience,
                    target_responder_id,
                    title,
                    message,
                    severity,
                    delivery_status,
                    1 if requires_human_approval else 0,
                    now_iso,
                ),
            )

        return InAppNotificationResponse(
            notification_id=notif_id,
            task_id=task_id,
            report_id=report_id,
            target_audience=target_audience,
            target_responder_id=target_responder_id,
            title=title,
            message=message,
            severity=severity,
            delivery_status=delivery_status,
            requires_human_approval=requires_human_approval,
            created_at=now_iso,
        )

    def list_notifications(
        self,
        target_audience: str | None = None,
        responder_id: str | None = None,
        limit: int = 50,
    ) -> list[InAppNotificationResponse]:
        """Queries in-app notifications."""
        query = "SELECT * FROM in_app_notifications WHERE 1=1"
        params: list[Any] = []

        if target_audience and target_audience != "all":
            query += " AND target_audience = ?"
            params.append(target_audience)

        if responder_id:
            query += " AND (target_responder_id = ? OR target_audience = 'public_advisory')"
            params.append(responder_id)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        return [
            InAppNotificationResponse(
                notification_id=r["notification_id"],
                task_id=r["task_id"],
                report_id=r["report_id"],
                target_audience=r["target_audience"],
                target_responder_id=r["target_responder_id"],
                title=r["title"],
                message=r["message"],
                severity=r["severity"],
                delivery_status=r["delivery_status"],
                requires_human_approval=bool(r["requires_human_approval"]),
                approved_by=r["approved_by"],
                approved_at=r["approved_at"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def approve_public_alert(
        self,
        notification_id: str,
        operator_id: str = "BBMP_Chief_Duty_Officer",
    ) -> InAppNotificationResponse:
        """Human operator approval gate for public/emergency alerts before delivery."""
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE in_app_notifications
                SET delivery_status = 'delivered_in_app', approved_by = ?, approved_at = ?
                WHERE notification_id = ? AND requires_human_approval = 1
                """,
                (operator_id, now_iso, notification_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(
                    f"Notification '{notification_id}' not found or does not require operator approval."
                )

            cursor.execute(
                "SELECT * FROM in_app_notifications WHERE notification_id = ?",
                (notification_id,),
            )
            r = cursor.fetchone()

        return InAppNotificationResponse(
            notification_id=r["notification_id"],
            task_id=r["task_id"],
            report_id=r["report_id"],
            target_audience=r["target_audience"],
            target_responder_id=r["target_responder_id"],
            title=r["title"],
            message=r["message"],
            severity=r["severity"],
            delivery_status=r["delivery_status"],
            requires_human_approval=bool(r["requires_human_approval"]),
            approved_by=r["approved_by"],
            approved_at=r["approved_at"],
            created_at=r["created_at"],
        )


# Global singleton instance
coordination_service = CoordinationService()
