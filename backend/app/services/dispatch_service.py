"""Municipal Response Coordination and Dispatch Service for FloodSense AI.

Manages operator verification of citizen reports, dewatering pump assignments,
traffic barricade orders, and response audit logging.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.database.db import get_db
from app.database.models import (
    CitizenReportResponse,
    MunicipalDispatchCreate,
    MunicipalDispatchResponse,
    VerificationActionRequest,
)
from app.demo.fixtures import SPOTS

SPOTS_BY_ID = {s.id: s for s in SPOTS}


class DispatchService:
    """Coordinates municipal disaster response and BBMP dewatering dispatches."""

    def verify_report(
        self,
        report_id: str,
        action_req: VerificationActionRequest,
    ) -> CitizenReportResponse:
        """Verifies or rejects a citizen report in SQLite."""
        new_status = "verified" if action_req.action == "verify" else "rejected"
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE citizen_reports
                SET verification_status = ?, verified_at = ?, verified_by = ?, notes = coalesce(notes, '') || ?
                WHERE report_id = ?
                """,
                (
                    new_status,
                    now_iso,
                    action_req.operator_id,
                    f" [Verified Note: {action_req.notes}]" if action_req.notes else "",
                    report_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Citizen report '{report_id}' not found.")

            # Audit log
            cursor.execute(
                """
                INSERT INTO response_audit_log (event_timestamp, action, actor_role, details_json)
                VALUES (?, 'report_verified', 'municipal_operator', ?)
                """,
                (now_iso, json.dumps({"report_id": report_id, "status": new_status, "by": action_req.operator_id})),
            )

            # Retrieve updated row
            cursor.execute("SELECT * FROM citizen_reports WHERE report_id = ?", (report_id,))
            r = cursor.fetchone()

        spot = SPOTS_BY_ID.get(r["spot_id"])
        img_url = f"/static/uploads/{r['image_filename']}" if r["image_filename"] else None
        return CitizenReportResponse(
            report_id=r["report_id"],
            spot_id=r["spot_id"],
            spot_name=spot.name if spot else r["spot_id"],
            report_type=r["report_type"],
            water_depth_cm=r["water_depth_cm"],
            severity=r["severity"],
            latitude=r["latitude"],
            longitude=r["longitude"],
            image_url=img_url,
            reporter_alias=r["reporter_alias"] or "Anonymous Citizen",
            verification_status=r["verification_status"],
            verified_at=r["verified_at"],
            verified_by=r["verified_by"],
            notes=r["notes"],
            created_at=r["created_at"],
        )

    def create_dispatch(self, dispatch_data: MunicipalDispatchCreate) -> MunicipalDispatchResponse:
        """Issues a new municipal dewatering or barricade directive."""
        spot = SPOTS_BY_ID.get(dispatch_data.spot_id)
        if not spot:
            raise ValueError(f"Unknown spot_id '{dispatch_data.spot_id}'.")

        dispatch_id = f"disp_{uuid.uuid4().hex[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO municipal_dispatches (
                    dispatch_id, spot_id, report_id, directive_type, priority,
                    status, location_name, capacity_gpm, action_instructions,
                    assigned_team, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'ordered', ?, ?, ?, ?, ?, ?)
                """,
                (
                    dispatch_id,
                    dispatch_data.spot_id,
                    dispatch_data.report_id,
                    dispatch_data.directive_type,
                    dispatch_data.priority,
                    spot.name,
                    dispatch_data.capacity_gpm or "500 GPM",
                    dispatch_data.action_instructions,
                    dispatch_data.assigned_team or "BBMP Stormwater Rapid Response",
                    now_iso,
                    now_iso,
                ),
            )
            # Log audit
            cursor.execute(
                """
                INSERT INTO response_audit_log (event_timestamp, action, actor_role, details_json)
                VALUES (?, 'dispatch_created', 'municipal_operator', ?)
                """,
                (now_iso, json.dumps({"dispatch_id": dispatch_id, "spot_id": dispatch_data.spot_id, "type": dispatch_data.directive_type})),
            )

        return MunicipalDispatchResponse(
            dispatch_id=dispatch_id,
            spot_id=dispatch_data.spot_id,
            location_name=spot.name,
            report_id=dispatch_data.report_id,
            directive_type=dispatch_data.directive_type,
            priority=dispatch_data.priority,
            status="ordered",
            capacity_gpm=dispatch_data.capacity_gpm,
            assigned_team=dispatch_data.assigned_team,
            action_instructions=dispatch_data.action_instructions,
            created_at=now_iso,
            updated_at=now_iso,
        )

    def list_dispatches(self, status: str | None = None, spot_id: str | None = None) -> list[MunicipalDispatchResponse]:
        """Lists active and historical municipal dispatches."""
        query = "SELECT * FROM municipal_dispatches WHERE 1=1"
        params: list[Any] = []

        if status and status != "all":
            query += " AND status = ?"
            params.append(status)

        if spot_id:
            query += " AND spot_id = ?"
            params.append(spot_id)

        query += " ORDER BY created_at DESC"

        results: list[MunicipalDispatchResponse] = []
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            for r in cursor.fetchall():
                results.append(
                    MunicipalDispatchResponse(
                        dispatch_id=r["dispatch_id"],
                        spot_id=r["spot_id"],
                        location_name=r["location_name"],
                        report_id=r["report_id"],
                        directive_type=r["directive_type"],
                        priority=r["priority"],
                        status=r["status"],
                        capacity_gpm=r["capacity_gpm"],
                        assigned_team=r["assigned_team"],
                        action_instructions=r["action_instructions"],
                        created_at=r["created_at"],
                        updated_at=r["updated_at"],
                    )
                )
        return results

    def update_dispatch_status(
        self,
        dispatch_id: str,
        status: str,
        operator_id: str = "BBMP_Control_Cell",
    ) -> MunicipalDispatchResponse:
        """Updates the operational status of a dispatch directive."""
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE municipal_dispatches
                SET status = ?, updated_at = ?
                WHERE dispatch_id = ?
                """,
                (status, now_iso, dispatch_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Dispatch directive '{dispatch_id}' not found.")

            cursor.execute(
                """
                INSERT INTO response_audit_log (event_timestamp, action, actor_role, details_json)
                VALUES (?, 'dispatch_status_updated', 'municipal_operator', ?)
                """,
                (now_iso, json.dumps({"dispatch_id": dispatch_id, "status": status, "by": operator_id})),
            )

            cursor.execute("SELECT * FROM municipal_dispatches WHERE dispatch_id = ?", (dispatch_id,))
            r = cursor.fetchone()

        return MunicipalDispatchResponse(
            dispatch_id=r["dispatch_id"],
            spot_id=r["spot_id"],
            location_name=r["location_name"],
            report_id=r["report_id"],
            directive_type=r["directive_type"],
            priority=r["priority"],
            status=r["status"],
            capacity_gpm=r["capacity_gpm"],
            assigned_team=r["assigned_team"],
            action_instructions=r["action_instructions"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )


# Global singleton instance
dispatch_service = DispatchService()

