"""Municipal Operator Triage & Verification Service for FloodSense AI.

Enriches incoming citizen reports with duplicate warnings, spatial cluster analysis,
and executes operator decisions with comprehensive audit logging.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from app.database.models import CitizenReportResponse, OperatorReportItem
from app.demo.fixtures import SPOTS
from app.services.citizen_service import citizen_service
from app.services.evidence_service import haversine_distance_meters

SPOTS_BY_ID = {s.id: s for s in SPOTS}


class OperatorService:
    """Manages operator verification queue and duplicate detection."""

    def list_operator_queue(
        self,
        status: str | None = None,
        limit: int = 100,
    ) -> list[OperatorReportItem]:
        """Returns reports enriched with spatial proximity and duplicate alerts."""
        reports = citizen_service.list_reports(status=status, limit=limit)
        enriched: list[OperatorReportItem] = []

        for i, rep in enumerate(reports):
            nearby_count = 0
            potential_dup_id: str | None = None
            dup_warning: str | None = None

            try:
                rep_dt = datetime.fromisoformat(rep.created_at.replace("Z", "+00:00"))
            except Exception:
                rep_dt = datetime.now(timezone.utc)

            # Check other reports for proximity and duplicate clustering
            for other in reports:
                if other.report_id == rep.report_id:
                    continue

                dist_m = haversine_distance_meters(
                    rep.latitude, rep.longitude, other.latitude, other.longitude
                )

                try:
                    other_dt = datetime.fromisoformat(other.created_at.replace("Z", "+00:00"))
                    time_diff_hours = abs((rep_dt - other_dt).total_seconds()) / 3600.0
                except Exception:
                    time_diff_hours = 999.0

                # Count nearby reports within 1.5 km and 6 hours
                if dist_m <= 1500.0 and time_diff_hours <= 6.0:
                    nearby_count += 1

                # Detect potential duplicate: within 500m and within 2 hours
                if dist_m <= 500.0 and time_diff_hours <= 2.0:
                    potential_dup_id = other.report_id
                    dist_str = f"{int(dist_m)}m" if dist_m >= 10 else "same spot"
                    time_str = f"{int(time_diff_hours * 60)}m" if time_diff_hours < 1 else f"{time_diff_hours:.1f}h"
                    dup_warning = (
                        f"Potential duplicate of {other.report_id} "
                        f"({dist_str} distance, submitted {time_str} apart)"
                    )

            enriched.append(
                OperatorReportItem(
                    report_id=rep.report_id,
                    spot_id=rep.spot_id,
                    spot_name=rep.spot_name,
                    report_type=rep.report_type,
                    water_depth_cm=rep.water_depth_cm,
                    severity=rep.severity,
                    severity_level=rep.severity_level,
                    latitude=rep.latitude,
                    longitude=rep.longitude,
                    image_url=rep.image_url,
                    reporter_alias=rep.reporter_alias,
                    verification_status=rep.verification_status,
                    verified_at=rep.verified_at,
                    verified_by=rep.verified_by,
                    notes=rep.notes,
                    duplicate_of_id=rep.duplicate_of_id,
                    decision_reason=rep.decision_reason,
                    created_at=rep.created_at,
                    nearby_reports_count=nearby_count,
                    potential_duplicate_of=potential_dup_id,
                    duplicate_warning=dup_warning,
                )
            )

        return enriched

    def execute_decision(
        self,
        report_id: str,
        decision: str,
        reviewer_id: str = "BBMP_Control_Operator",
        reason: str | None = None,
        duplicate_of_id: str | None = None,
    ) -> CitizenReportResponse:
        """Executes verification action with reviewer tracking."""
        updated = citizen_service.update_verification(
            report_id=report_id,
            action=decision,
            operator_id=reviewer_id,
            reason=reason,
            duplicate_of_id=duplicate_of_id,
            notes=reason,
        )
        if not updated:
            raise ValueError(f"Report '{report_id}' not found.")
        return updated

    def link_duplicate(
        self,
        report_id: str,
        parent_report_id: str,
        reviewer_id: str = "BBMP_Control_Operator",
        reason: str | None = None,
    ) -> CitizenReportResponse:
        """Marks report as duplicate of another report."""
        return citizen_service.link_duplicate(
            report_id=report_id,
            parent_report_id=parent_report_id,
            operator_id=reviewer_id,
            reason=reason or f"Linked as duplicate of {parent_report_id}",
        )


# Global singleton instance
operator_service = OperatorService()

