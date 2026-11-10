"""Operational Evidence Overlay Service for FloodSense AI.

Consumes human-verified citizen reports and associates them with pilot locations
using configurable geographic proximity and time windows.

CRITICAL ARCHITECTURAL ISOLATION RULE:
- Does NOT alter PhysicalRiskModel formula or risk thresholds.
- Does NOT alter historical incident records or retrospective reanalysis metrics.
- Exposes verified citizen evidence as an independent operational overlay signal.
- Pending reports are tracked separately and NEVER counted as verified flood evidence.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import Any
from pathlib import Path

from app.database.db import get_db
from app.database.models import (
    CitizenReportResponse,
    EvidenceConfidence,
    EvidenceFreshness,
    EvidenceStatus,
    OperationalEvidenceResponse,
)
from app.demo.fixtures import SPOTS
from app.services.citizen_service import citizen_service

SPOTS_BY_ID = {s.id: s for s in SPOTS}


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two GPS coordinates in meters."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


class OperationalEvidenceService:
    """Computes verified citizen intelligence overlays per monitored spot."""

    def __init__(self, default_radius_meters: float = 1500.0, default_window_hours: float = 6.0):
        self.default_radius_meters = default_radius_meters
        self.default_window_hours = default_window_hours

    def get_spot_evidence(
        self,
        spot_id: str,
        radius_meters: float | None = None,
        window_hours: float | None = None,
        as_of_time: datetime | str | None = None,
    ) -> OperationalEvidenceResponse:
        """Calculates evidence overlay for a specific monitored spot."""
        spot = SPOTS_BY_ID.get(spot_id)
        if not spot:
            raise ValueError(f"Spot '{spot_id}' not found in registered study spots.")

        radius = radius_meters if radius_meters is not None else self.default_radius_meters
        window = window_hours if window_hours is not None else self.default_window_hours

        # Resolve reference timestamp
        if as_of_time is None:
            ref_dt = datetime.now(timezone.utc)
        elif isinstance(as_of_time, str):
            ref_dt = datetime.fromisoformat(as_of_time.replace("Z", "+00:00"))
            if ref_dt.tzinfo is None:
                ref_dt = ref_dt.replace(tzinfo=timezone.utc)
        else:
            ref_dt = as_of_time if as_of_time.tzinfo else as_of_time.replace(tzinfo=timezone.utc)

        cutoff_dt = ref_dt - timedelta(hours=window)

        # Retrieve all reports from SQLite
        all_reports = citizen_service.list_reports(limit=200)

        approved_nearby: list[CitizenReportResponse] = []
        pending_nearby: list[CitizenReportResponse] = []

        seen_duplicate_groups: set[str] = set()

        for rep in all_reports:
            # Geographic proximity check
            dist = haversine_distance_meters(rep.latitude, rep.longitude, spot.lat, spot.lng)
            is_nearby = dist <= radius or rep.spot_id == spot.id

            if not is_nearby:
                continue

            # Parse report creation / verification timestamp
            try:
                rep_dt = datetime.fromisoformat(rep.created_at.replace("Z", "+00:00"))
                if rep_dt.tzinfo is None:
                    rep_dt = rep_dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            # Time-window filtering: reports older than cutoff are expired
            if rep_dt < cutoff_dt or rep_dt > ref_dt:
                continue

            # Classify by verification status (only verified flood incidents constitute positive flood evidence)
            if rep.verification_status in ("approved", "verified") and rep.report_type == "flood":
                # Deduplication check: skip if explicitly linked as duplicate
                if rep.duplicate_of_id:
                    continue

                # Spatio-temporal cluster deduplication (within 300m and 30min)
                cluster_key = f"{round(rep.latitude, 3)}_{round(rep.longitude, 3)}"
                if cluster_key in seen_duplicate_groups:
                    continue
                seen_duplicate_groups.add(cluster_key)

                approved_nearby.append(rep)

            elif rep.verification_status in ("submitted", "pending", "under_review"):
                # Pending reports tracked separately - never counted as approved evidence
                pending_nearby.append(rep)

        # Compute Freshness & Latest timestamp
        latest_verified_at: str | None = None
        freshness: EvidenceFreshness = "none"

        if approved_nearby:
            # Sort by created_at desc
            approved_nearby.sort(key=lambda r: r.created_at, reverse=True)
            latest_rep = approved_nearby[0]
            latest_verified_at = latest_rep.verified_at or latest_rep.created_at

            try:
                lat_dt = datetime.fromisoformat(latest_rep.created_at.replace("Z", "+00:00"))
                if lat_dt.tzinfo is None:
                    lat_dt = lat_dt.replace(tzinfo=timezone.utc)
                age_hours = (ref_dt - lat_dt).total_seconds() / 3600.0

                if age_hours <= 2.0:
                    freshness = "fresh"
                elif age_hours <= 6.0:
                    freshness = "recent"
                elif age_hours <= 24.0:
                    freshness = "decayed"
                else:
                    freshness = "expired"
            except Exception:
                freshness = "recent"

        # Compute Evidence Status
        n_approved = len(approved_nearby)
        has_critical_depth = any((r.water_depth_cm or 0) >= 80.0 or r.severity == 4 for r in approved_nearby)

        if n_approved == 0:
            evidence_status: EvidenceStatus = "none"
        elif has_critical_depth or n_approved >= 4:
            evidence_status = "critical"
        elif n_approved >= 2 or any(r.severity == 3 for r in approved_nearby):
            evidence_status = "elevated"
        else:
            evidence_status = "watch"

        # Compute Confidence
        if n_approved == 0:
            confidence: EvidenceConfidence = "none"
        elif n_approved >= 2 or any(r.image_url is not None for r in approved_nearby):
            confidence = "high"
        elif any((r.water_depth_cm or 0) >= 30.0 for r in approved_nearby):
            confidence = "medium"
        else:
            confidence = "low"

        # Generate transparent explanation
        approved_ids = [r.report_id for r in approved_nearby]
        pending_ids = [r.report_id for r in pending_nearby]

        if n_approved > 0:
            explanation = (
                f"{n_approved} human-verified citizen report{'s' if n_approved > 1 else ''} "
                f"within {int(radius)}m of {spot.name} in the past {window:.1f}h "
                f"(latest verified evidence at {latest_verified_at}). "
                f"Freshness: {freshness}, Confidence: {confidence}."
            )
            if pending_nearby:
                explanation += f" ({len(pending_nearby)} unverified pending reports nearby)."
        else:
            explanation = (
                f"No human-verified flood reports within {int(radius)}m of {spot.name} "
                f"in the past {window:.1f}h."
            )
            if pending_nearby:
                explanation += f" However, {len(pending_nearby)} unverified community report{'s are' if len(pending_nearby) > 1 else ' is'} currently under review."

        return OperationalEvidenceResponse(
            spot_id=spot.id,
            spot_name=spot.name,
            approved_reports_nearby=n_approved,
            pending_reports_nearby=len(pending_nearby),
            latest_verified_at=latest_verified_at,
            evidence_status=evidence_status,
            confidence=confidence,
            freshness=freshness,
            source="human_verified_citizen_reports",
            radius_meters=radius,
            window_hours=window,
            explanation=explanation,
            approved_report_ids=approved_ids,
            pending_report_ids=pending_ids,
        )

    def get_all_spots_evidence(
        self,
        radius_meters: float | None = None,
        window_hours: float | None = None,
        as_of_time: datetime | str | None = None,
    ) -> list[OperationalEvidenceResponse]:
        """Calculates evidence overlays for all registered pilot spots."""
        return [
            self.get_spot_evidence(
                spot_id=s.id,
                radius_meters=radius_meters,
                window_hours=window_hours,
                as_of_time=as_of_time,
            )
            for s in SPOTS
        ]


# Global singleton instance
evidence_service = OperationalEvidenceService()

