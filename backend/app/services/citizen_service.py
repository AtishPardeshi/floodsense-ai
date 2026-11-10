"""Citizen reporting and crowdsourced intelligence service for FloodSense AI.

Handles citizen flood reports and verified clear controls, photo uploads,
audit logging, and persistence in local SQLite database.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database.db import get_db
from app.database.migrations import run_startup_migrations
from app.database.models import CitizenReportCreate, CitizenReportResponse
from app.demo.fixtures import SPOTS

ROOT = Path(__file__).resolve().parents[3]
UPLOADS_DIR = ROOT / "data" / "uploads" / "reports"
SPOTS_BY_ID = {s.id: s for s in SPOTS}


SEVERITY_MAP: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
INV_SEVERITY_MAP: dict[int, str] = {v: k for k, v in SEVERITY_MAP.items()}


class CitizenService:
    """Manages crowdsourced citizen flood and clear-pass intelligence."""

    def __init__(self, uploads_dir: Path | None = None):
        self.uploads_dir = uploads_dir or UPLOADS_DIR
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        run_startup_migrations()

    def save_image(self, file_bytes: bytes, filename: str) -> str:
        """Validates and saves uploaded photo to disk with a sanitized UUID filename."""
        if len(file_bytes) > 5 * 1024 * 1024:
            raise ValueError("Uploaded image exceeds maximum allowable limit of 5 MB.")

        # Basic magic bytes check for jpeg, png, webp
        is_jpeg = file_bytes.startswith(b"\xff\xd8\xff")
        is_png = file_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        is_webp = len(file_bytes) > 12 and file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP"

        if not (is_jpeg or is_png or is_webp):
            # Check extension fallback if bytes header check is ambiguous
            ext_lower = Path(filename).suffix.lower()
            if ext_lower not in {".jpg", ".jpeg", ".png", ".webp"}:
                raise ValueError("Unsupported image format. Allowed formats: JPEG, PNG, WebP.")
            ext = ext_lower
        else:
            ext = ".png" if is_png else (".webp" if is_webp else ".jpg")

        saved_name = f"rep_{uuid.uuid4().hex[:12]}{ext}"
        target_path = self.uploads_dir / saved_name
        target_path.write_bytes(file_bytes)
        return saved_name

    def create_report(
        self,
        report_data: CitizenReportCreate,
        image_bytes: bytes | None = None,
        image_filename: str | None = None,
    ) -> CitizenReportResponse:
        """Persists a new citizen flood or clear control report into SQLite."""
        # Resolve spot and coordinates
        spot_id = report_data.spot_id
        spot = SPOTS_BY_ID.get(spot_id) if spot_id else None

        if spot:
            lat = report_data.latitude if report_data.latitude is not None else spot.lat
            lng = report_data.longitude if report_data.longitude is not None else spot.lng
            spot_name = spot.name
        else:
            # Coordinates must be present if spot_id is omitted or custom
            if report_data.latitude is None or report_data.longitude is None:
                # Default to Silk Board if neither provided
                nearest = SPOTS[0]
                lat = nearest.lat
                lng = nearest.lng
                spot_id = nearest.id
                spot_name = nearest.name
            else:
                lat = float(report_data.latitude)
                lng = float(report_data.longitude)
                # Find closest monitored spot
                nearest = min(SPOTS, key=lambda s: (s.lat - lat) ** 2 + (s.lng - lng) ** 2)
                spot_id = report_data.spot_id or nearest.id
                spot_name = f"Near {nearest.name}"

        # Determine severity and severity_level
        if report_data.report_type == "control_clear":
            sev = None
            sev_level = None
        elif report_data.severity_level and report_data.severity_level in SEVERITY_MAP:
            sev_level = report_data.severity_level
            sev = SEVERITY_MAP[sev_level]
        elif report_data.severity is not None:
            sev = max(1, min(4, int(report_data.severity)))
            sev_level = INV_SEVERITY_MAP.get(sev, "medium")
        elif report_data.water_depth_cm is not None:
            if report_data.water_depth_cm >= 90.0:
                sev = 4
            elif report_data.water_depth_cm >= 50.0:
                sev = 3
            elif report_data.water_depth_cm >= 20.0:
                sev = 2
            else:
                sev = 1
            sev_level = INV_SEVERITY_MAP.get(sev, "medium")
        else:
            sev = 2
            sev_level = "medium"

        saved_img_name: str | None = None
        if image_bytes and image_filename:
            saved_img_name = self.save_image(image_bytes, image_filename)

        report_id = f"rep_{uuid.uuid4().hex[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO citizen_reports (
                    report_id, spot_id, report_type, water_depth_cm, severity, severity_level,
                    latitude, longitude, image_filename, reporter_alias,
                    verification_status, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'submitted', ?, ?)
                """,
                (
                    report_id,
                    spot_id,
                    report_data.report_type,
                    report_data.water_depth_cm,
                    sev,
                    sev_level,
                    lat,
                    lng,
                    saved_img_name,
                    report_data.reporter_alias or "Anonymous Citizen",
                    report_data.notes,
                    now_iso,
                ),
            )
            cursor.execute(
                """
                INSERT INTO response_audit_log (event_timestamp, action, actor_role, details_json)
                VALUES (?, 'citizen_report_created', 'citizen', ?)
                """,
                (now_iso, json.dumps({"report_id": report_id, "spot_id": spot_id, "type": report_data.report_type})),
            )

        img_url = f"/static/uploads/{saved_img_name}" if saved_img_name else None

        return CitizenReportResponse(
            report_id=report_id,
            spot_id=spot_id,
            spot_name=spot_name,
            report_type=report_data.report_type,
            water_depth_cm=report_data.water_depth_cm,
            severity=sev,
            severity_level=sev_level,
            latitude=lat,
            longitude=lng,
            image_url=img_url,
            reporter_alias=report_data.reporter_alias or "Anonymous Citizen",
            verification_status="submitted",
            notes=report_data.notes,
            created_at=now_iso,
        )

    def update_verification(
        self,
        report_id: str,
        action: str,
        operator_id: str = "BBMP_Control_Cell",
        notes: str | None = None,
        reason: str | None = None,
        duplicate_of_id: str | None = None,
    ) -> CitizenReportResponse | None:
        """Updates verification status: submitted, under_review, approved, rejected, needs_info."""
        # Normalize action
        action_map = {
            "approve": "approved",
            "approved": "approved",
            "verify": "approved",
            "verified": "approved",
            "under_review": "under_review",
            "review": "under_review",
            "reject": "rejected",
            "rejected": "rejected",
            "needs_info": "needs_info",
            "needs_more_info": "needs_info",
            "submitted": "submitted",
        }
        new_status = action_map.get(action.lower().strip())
        if not new_status:
            raise ValueError(f"Invalid verification action '{action}'.")

        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        decision_reason = reason or notes

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE citizen_reports
                SET verification_status = ?, verified_at = ?, verified_by = ?,
                    decision_reason = COALESCE(?, decision_reason),
                    duplicate_of_id = COALESCE(?, duplicate_of_id),
                    notes = CASE WHEN ? IS NOT NULL THEN COALESCE(notes || ' | ', '') || ? ELSE notes END
                WHERE report_id = ?
                """,
                (new_status, now_iso, operator_id, decision_reason, duplicate_of_id, notes, notes, report_id),
            )
            if cursor.rowcount == 0:
                return None

            cursor.execute(
                """
                INSERT INTO response_audit_log (event_timestamp, action, actor_role, details_json)
                VALUES (?, 'citizen_report_verified', 'municipal_operator', ?)
                """,
                (
                    now_iso,
                    json.dumps(
                        {
                            "report_id": report_id,
                            "status": new_status,
                            "operator_id": operator_id,
                            "decision_reason": decision_reason,
                            "duplicate_of_id": duplicate_of_id,
                        }
                    ),
                ),
            )

        return self.get_report(report_id)

    def link_duplicate(
        self,
        report_id: str,
        parent_report_id: str,
        operator_id: str = "BBMP_Control_Cell",
        reason: str | None = "Linked as duplicate by municipal operator",
    ) -> CitizenReportResponse | None:
        """Marks a report as a duplicate of an existing primary report."""
        if report_id == parent_report_id:
            raise ValueError("A report cannot be marked as a duplicate of itself.")

        parent = self.get_report(parent_report_id)
        if not parent:
            raise ValueError(f"Parent report '{parent_report_id}' does not exist.")

        return self.update_verification(
            report_id=report_id,
            action="rejected",  # duplicates are excluded from active evidence
            operator_id=operator_id,
            notes=f"Duplicate of {parent_report_id}",
            reason=reason or f"Duplicate of {parent_report_id}",
            duplicate_of_id=parent_report_id,
        )

    def list_reports(
        self,
        spot_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[CitizenReportResponse]:
        """Queries reports from SQLite with optional filtering."""
        query = "SELECT * FROM citizen_reports WHERE 1=1"
        params: list[Any] = []

        if spot_id:
            query += " AND spot_id = ?"
            params.append(spot_id)

        if status and status != "all":
            query += " AND verification_status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        results: list[CitizenReportResponse] = []
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            for r in rows:
                spot = SPOTS_BY_ID.get(r["spot_id"])
                img_url = f"/static/uploads/{r['image_filename']}" if r["image_filename"] else None
                s_level = r["severity_level"] if "severity_level" in r.keys() and r["severity_level"] else INV_SEVERITY_MAP.get(r["severity"], "medium")
                dup_of = r["duplicate_of_id"] if "duplicate_of_id" in r.keys() else None
                dec_reason = r["decision_reason"] if "decision_reason" in r.keys() else None
                results.append(
                    CitizenReportResponse(
                        report_id=r["report_id"],
                        spot_id=r["spot_id"],
                        spot_name=spot.name if spot else r["spot_id"],
                        report_type=r["report_type"],
                        water_depth_cm=r["water_depth_cm"],
                        severity=r["severity"],
                        severity_level=s_level,
                        latitude=r["latitude"],
                        longitude=r["longitude"],
                        image_url=img_url,
                        reporter_alias=r["reporter_alias"] or "Anonymous Citizen",
                        verification_status=r["verification_status"],
                        verified_at=r["verified_at"],
                        verified_by=r["verified_by"],
                        notes=r["notes"],
                        duplicate_of_id=dup_of,
                        decision_reason=dec_reason,
                        created_at=r["created_at"],
                    )
                )
        return results

    def get_report(self, report_id: str) -> CitizenReportResponse | None:
        """Retrieves a single report by ID."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM citizen_reports WHERE report_id = ?", (report_id,))
            r = cursor.fetchone()
            if not r:
                return None
            spot = SPOTS_BY_ID.get(r["spot_id"])
            img_url = f"/static/uploads/{r['image_filename']}" if r["image_filename"] else None
            s_level = r["severity_level"] if "severity_level" in r.keys() and r["severity_level"] else INV_SEVERITY_MAP.get(r["severity"], "medium")
            dup_of = r["duplicate_of_id"] if "duplicate_of_id" in r.keys() else None
            dec_reason = r["decision_reason"] if "decision_reason" in r.keys() else None
            return CitizenReportResponse(
                report_id=r["report_id"],
                spot_id=r["spot_id"],
                spot_name=spot.name if spot else r["spot_id"],
                report_type=r["report_type"],
                water_depth_cm=r["water_depth_cm"],
                severity=r["severity"],
                severity_level=s_level,
                latitude=r["latitude"],
                longitude=r["longitude"],
                image_url=img_url,
                reporter_alias=r["reporter_alias"] or "Anonymous Citizen",
                verification_status=r["verification_status"],
                verified_at=r["verified_at"],
                verified_by=r["verified_by"],
                notes=r["notes"],
                duplicate_of_id=dup_of,
                decision_reason=dec_reason,
                created_at=r["created_at"],
            )


# Global singleton instance
citizen_service = CitizenService()
