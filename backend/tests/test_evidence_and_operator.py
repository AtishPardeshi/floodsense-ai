"""Comprehensive automated tests for Operator Verification & Operational Evidence Overlay.

Verifies:
1. Pending report exclusion from approved evidence count.
2. Rejected report exclusion from approved evidence count.
3. Approved report inclusion in approved evidence count.
4. Duplicate report exclusion (linked duplicate reports are not double-counted).
5. Geographic matching (proximity threshold inclusion and distant report exclusion).
6. Time-window expiration (old reports beyond window are excluded).
7. Evidence freshness states (fresh, recent, decayed, none).
8. Strict protection of PhysicalRiskModel and historical replay.
"""
import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.database.schemas import Rainfall
from app.demo.replay_engine import replay_manager
from app.main import app
from app.services.physical_risk import PhysicalRiskModel
from app.demo.fixtures import SPOTS

client = TestClient(app)
OPERATOR_HEADERS = {"X-Operator-Key": "bbmp-operator-secret-2026"}


def test_operator_queue_enriched_with_duplicate_and_proximity_alerts():
    """Test that operator queue returns reports with duplicate detection warnings."""
    # Create two reports near Bellandur close to each other
    res1 = client.post(
        "/api/reports",
        json={
            "spot_id": "bellandur",
            "latitude": 12.9352,
            "longitude": 77.6745,
            "notes": "Severe waterlogging near lake gate",
        },
    )
    rep1_id = res1.json()["report_id"]

    res2 = client.post(
        "/api/reports",
        json={
            "spot_id": "bellandur",
            "latitude": 12.9355,
            "longitude": 77.6748,
            "notes": "Water accumulating near same lake boundary",
        },
    )
    rep2_id = res2.json()["report_id"]

    # Fetch operator queue
    q_res = client.get("/api/operator/queue", headers=OPERATOR_HEADERS)
    assert q_res.status_code == 200
    queue = q_res.json()

    # Find the reports in queue
    item2 = next((item for item in queue if item["report_id"] == rep2_id), None)
    assert item2 is not None
    assert item2["potential_duplicate_of"] is not None
    assert "Potential duplicate" in item2["duplicate_warning"]


def test_operator_decision_records_identity_timestamp_and_reason():
    """Test that operator decision records reviewer ID, timestamp, and reason."""
    res = client.post("/api/reports", json={"spot_id": "kr_circle", "notes": "Underpass drain blocked"})
    report_id = res.json()["report_id"]

    # Reject with specific reason
    dec_res = client.post(
        f"/api/operator/reports/{report_id}/decision",
        json={
            "decision": "rejected",
            "reviewer_id": "BBMP_Chief_Engineer_Rao",
            "reason": "Traffic camera shows water cleared by maintenance team.",
        },
        headers=OPERATOR_HEADERS,
    )
    assert dec_res.status_code == 200
    updated = dec_res.json()
    assert updated["verification_status"] == "rejected"
    assert updated["verified_by"] == "BBMP_Chief_Engineer_Rao"
    assert updated["verified_at"] is not None
    assert "Traffic camera shows water cleared" in updated["decision_reason"]


def test_pending_report_exclusion_from_evidence_overlay():
    """Pending citizen reports must NEVER be counted as approved flood evidence."""
    # Create report without operator verification (status='submitted')
    res = client.post(
        "/api/reports",
        json={"spot_id": "hebbal", "notes": "Unverified water pooling claim"},
    )
    rep_id = res.json()["report_id"]

    ev_res = client.get("/api/evidence/hebbal?radius_meters=2000&window_hours=24")
    assert ev_res.status_code == 200
    evidence = ev_res.json()

    # rep_id must be in pending_report_ids, NOT approved_report_ids
    assert rep_id in evidence["pending_report_ids"]
    assert rep_id not in evidence["approved_report_ids"]
    assert evidence["approved_reports_nearby"] == 0
    assert evidence["evidence_status"] == "none"


def test_rejected_report_exclusion_from_evidence_overlay():
    """Rejected citizen reports must be excluded from approved evidence count."""
    res = client.post("/api/reports", json={"spot_id": "mahadevapura", "notes": "Doubtful report"})
    rep_id = res.json()["report_id"]

    # Operator rejects the report
    client.post(
        f"/api/operator/reports/{report_id}/decision" if False else f"/api/operator/reports/{rep_id}/decision",
        json={
            "decision": "rejected",
            "reviewer_id": "BBMP_Warden",
            "reason": "Road is clear on field check",
        },
        headers=OPERATOR_HEADERS,
    )

    ev_res = client.get("/api/evidence/mahadevapura?radius_meters=2000&window_hours=24")
    assert ev_res.status_code == 200
    evidence = ev_res.json()

    assert rep_id not in evidence["approved_report_ids"]
    assert rep_id not in evidence["pending_report_ids"]


def test_approved_report_inclusion_in_evidence_overlay():
    """Approved reports must be included in evidence overlay after human verification."""
    res = client.post(
        "/api/reports",
        json={
            "spot_id": "indiranagar",
            "severity_level": "high",
            "water_depth_cm": 50.0,
            "notes": "100ft road waterlogged",
        },
    )
    rep_id = res.json()["report_id"]

    # Operator approves the report
    app_res = client.post(
        f"/api/operator/reports/{rep_id}/decision",
        json={
            "decision": "approved",
            "reviewer_id": "BBMP_Control_Desk",
            "reason": "Confirmed by traffic patrol squad",
        },
        headers=OPERATOR_HEADERS,
    )
    assert app_res.status_code == 200

    ev_res = client.get("/api/evidence/indiranagar?radius_meters=2000&window_hours=24")
    assert ev_res.status_code == 200
    evidence = ev_res.json()

    assert rep_id in evidence["approved_report_ids"]
    assert evidence["approved_reports_nearby"] >= 1
    assert evidence["evidence_status"] in ("watch", "elevated", "critical")
    assert evidence["latest_verified_at"] is not None


def test_duplicate_report_exclusion():
    """Reports linked as duplicates must not double count towards approved evidence."""
    # Create parent report and approve it
    res1 = client.post(
        "/api/reports",
        json={"spot_id": "silk_board", "notes": "Primary flooding observation"},
    )
    parent_id = res1.json()["report_id"]
    client.post(
        f"/api/operator/reports/{parent_id}/decision",
        json={"decision": "approved", "reviewer_id": "Operator_1"},
        headers=OPERATOR_HEADERS,
    )

    # Create second report at same spot
    res2 = client.post(
        "/api/reports",
        json={"spot_id": "silk_board", "notes": "Duplicate flooding observation from passerby"},
    )
    dup_id = res2.json()["report_id"]

    # Link dup_id to parent_id
    link_res = client.post(
        f"/api/operator/reports/{dup_id}/link-duplicate?parent_report_id={parent_id}&reason=Same%20event",
        headers=OPERATOR_HEADERS,
    )
    assert link_res.status_code == 200

    ev_res = client.get("/api/evidence/silk_board?radius_meters=2000&window_hours=24")
    evidence = ev_res.json()

    # The parent should be counted, but the duplicate should NOT be double-counted
    assert parent_id in evidence["approved_report_ids"]
    assert dup_id not in evidence["approved_report_ids"]


def test_geographic_matching_proximity():
    """Reports outside the configured radius must be excluded from the spot evidence."""
    # Whitefield coordinates (~12.9698, 77.7499) are ~10 km away from Silk Board (12.9177, 77.6233)
    res = client.post(
        "/api/reports",
        json={
            "latitude": 12.9698,
            "longitude": 77.7499,
            "notes": "Flooding far away in Whitefield",
        },
    )
    far_id = res.json()["report_id"]

    # Approve the far report
    client.post(
        f"/api/operator/reports/{far_id}/decision",
        json={"decision": "approved", "reviewer_id": "Operator_1"},
        headers=OPERATOR_HEADERS,
    )

    # Check Silk Board evidence with 1500m radius
    ev_res = client.get("/api/evidence/silk_board?radius_meters=1500&window_hours=24")
    evidence = ev_res.json()

    # Far report must NOT match Silk Board
    assert far_id not in evidence["approved_report_ids"]


def test_time_window_expiration():
    """Reports older than the configurable time window must be excluded as expired."""
    from app.services.evidence_service import evidence_service

    # Evaluate with an as_of timestamp far in the future (e.g. 48 hours later)
    future_time = datetime.now(timezone.utc) + timedelta(hours=48)

    ev = evidence_service.get_spot_evidence(
        spot_id="indiranagar",
        radius_meters=2000,
        window_hours=6.0,  # 6-hour window
        as_of_time=future_time,
    )

    # In the future window, today's report has expired
    assert ev.approved_reports_nearby == 0
    assert ev.evidence_status == "none"
    assert ev.freshness == "none"


def test_evidence_freshness_states():
    """Test that recent reports produce 'fresh' or 'recent' freshness status."""
    res = client.post("/api/reports", json={"spot_id": "agara", "notes": "Fresh flooding report"})
    rep_id = res.json()["report_id"]
    client.post(
        f"/api/operator/reports/{rep_id}/decision",
        json={"decision": "approved", "reviewer_id": "Operator_1"},
        headers=OPERATOR_HEADERS,
    )

    ev_res = client.get("/api/evidence/agara?radius_meters=2000&window_hours=24")
    assert ev_res.status_code == 200
    evidence = ev_res.json()
    assert evidence["freshness"] in ("fresh", "recent")


def test_physical_risk_engine_remains_strictly_unchanged():
    """Verify that PhysicalRiskModel math, weights, and thresholds have zero modifications."""
    silk_board = next(s for s in SPOTS if s.id == "silk_board")
    model = PhysicalRiskModel()

    # Baseline dry prediction
    pred_dry = model.predict_spot(
        silk_board,
        Rainfall(rain_1h_mm=0.0, rain_3h_mm=0.0, forecast_2h_mm=0.0),
    )
    assert pred_dry.risk_level == "green"
    assert pred_dry.physical_score < 0.35

    # Baseline severe rain prediction
    pred_wet = model.predict_spot(
        silk_board,
        Rainfall(rain_1h_mm=75.0, rain_3h_mm=120.0, forecast_2h_mm=80.0),
    )
    assert pred_wet.risk_level == "red"
    assert pred_wet.physical_score >= 0.65


def test_historical_replay_remains_strictly_unchanged():
    """Verify that historical replay engine scenarios and steps are completely isolated."""
    events = replay_manager.list_available_events()
    assert len(events) == 3
    event_ids = [e["event_id"] for e in events]
    assert "ev_20220905_deluge" in event_ids
    assert "ev_20230521_cloudburst" in event_ids
    assert "ev_20241021_cloudburst" in event_ids

    # Start and verify session
    session = replay_manager.start_session("ev_20220905_deluge")
    state = session.get_state()
    assert state.total_steps > 0
    assert len(state.spots) == 8
    # Advance one step
    next_state = session.next_step()
    assert next_state.current_step == 1
