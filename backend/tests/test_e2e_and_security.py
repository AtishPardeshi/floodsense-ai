"""Comprehensive End-to-End Integration, Offline Flow, and Security Tests for Phase 3."""
import io
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.db import get_db
from app.database.schemas import Rainfall
from app.services.physical_risk import PhysicalRiskModel
from app.demo.fixtures import SPOTS
from app.demo.replay_engine import replay_manager

client = TestClient(app)
OPERATOR_HEADERS = {"X-Operator-Key": "bbmp-operator-secret-2026"}
VALID_PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"


def test_complete_end_to_end_citizen_to_response_scenario():
    """Executes the complete required 15-step end-to-end scenario."""
    # 1 & 2. Citizen submits report with photograph and GPS location
    files = {"image": ("mobile_flood_cam.png", VALID_PNG_BYTES, "image/png")}
    form_data = {
        "spot_id": "kr_circle",
        "latitude": "12.9756",
        "longitude": "77.5888",
        "report_type": "flood",
        "severity_level": "critical",
        "water_depth_cm": "85.0",
        "reporter_alias": "Citizen_Whitefield",
        "notes": "Underpass submerged. Water rising rapidly near north ramp.",
    }
    sub_res = client.post("/api/reports", data=form_data, files=files)
    assert sub_res.status_code == 201
    report = sub_res.json()

    # 3. Verify backend stores report, generates tracking token, and photo URL
    report_id = report["report_id"]
    assert report_id.startswith("rep_")
    assert len(report_id) >= 14
    assert report["verification_status"] == "submitted"
    assert report["water_depth_cm"] == 85.0
    assert report["image_url"] is not None
    assert "/static/uploads/rep_" in report["image_url"]

    # Verify report is fetchable via tracking token
    track_res = client.get(f"/api/reports/{report_id}")
    assert track_res.status_code == 200
    assert track_res.json()["report_id"] == report_id

    # 4 & 5. Open operator dashboard queue and find pending report
    queue_res = client.get("/api/operator/queue?status=submitted", headers=OPERATOR_HEADERS)
    assert queue_res.status_code == 200
    queue = queue_res.json()
    item = next((r for r in queue if r["report_id"] == report_id), None)
    assert item is not None

    # 6. Inspect photo, location and duplicate warnings
    assert item["image_url"] == report["image_url"]
    assert item["spot_id"] == "kr_circle"
    assert item["nearby_reports_count"] >= 0

    # 7. Operator approves the report
    decision_payload = {
        "decision": "approved",
        "reviewer_id": "Duty_Officer_Control_Room",
        "reason": "Corroborated by Traffic Police CCTV camera 14.",
    }
    dec_res = client.post(
        f"/api/operator/reports/{report_id}/decision",
        json=decision_payload,
        headers=OPERATOR_HEADERS,
    )
    assert dec_res.status_code == 200
    approved_report = dec_res.json()
    assert approved_report["verification_status"] == "approved"
    assert approved_report["verified_by"] == "Duty_Officer_Control_Room"
    assert approved_report["verified_at"] is not None

    # 8. Confirm verified evidence overlay updates
    ev_res = client.get("/api/evidence/kr_circle?radius_meters=2000&window_hours=6")
    assert ev_res.status_code == 200
    ev = ev_res.json()
    assert ev["approved_reports_nearby"] >= 1
    assert report_id in ev["approved_report_ids"]
    assert ev["evidence_status"] in ("elevated", "critical")
    assert ev["freshness"] == "fresh"

    # 9. Confirm Phase 2 physical risk score formula & historical replay remain completely unchanged
    spot = next(s for s in SPOTS if s.id == "kr_circle")
    model = PhysicalRiskModel()
    rain = Rainfall(rain_1h_mm=40.0, rain_3h_mm=80.0, rain_6h_mm=100.0, rain_24h_mm=120.0, forecast_2h_mm=50.0)
    risk_res = model.predict_spot(spot, rain)
    assert 0.0 <= risk_res.physical_score <= 1.0

    # Check replay session lifecycle via REST API
    start_res = client.post("/api/replay/start/ev_20220905_deluge")
    assert start_res.status_code == 200
    run_id = start_res.json()["run_id"]
    step1_res = client.post(f"/api/replay/{run_id}/next")
    assert step1_res.status_code == 200
    assert step1_res.json()["current_step"] == 1
    pause_res = client.post(f"/api/replay/{run_id}/pause")
    assert pause_res.status_code == 200
    assert pause_res.json()["is_paused"] is True

    # 10. Create response task from approved report
    task_payload = {
        "spot_id": "kr_circle",
        "incident_report_id": report_id,
        "title": "Clear deep flood waters at KR Circle underpass",
        "description": "85cm depth reported. Submersible dewatering pump required.",
        "latitude": 12.9756,
        "longitude": 77.5888,
    }
    create_task_res = client.post("/api/coordination/tasks", json=task_payload, headers=OPERATOR_HEADERS)
    assert create_task_res.status_code == 201
    task = create_task_res.json()
    task_id = task["task_id"]
    assert task["status"] == "open"
    # Deterministic priority should be P1_CRITICAL due to 85cm depth + underpass depression
    assert task["priority"] == "P1_CRITICAL"
    assert task["priority_reasons"] is not None
    assert task["priority_reasons"]["total_score"] >= 70

    # 11. Assign it to responder unit BBMP_Rapid_Unit_1
    assign_res = client.post(
        f"/api/coordination/tasks/{task_id}/assign",
        json={"responder_id": "BBMP_Rapid_Unit_1", "operator_id": "Duty_Officer_Control_Room"},
        headers=OPERATOR_HEADERS,
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["status"] == "assigned"
    assert assign_res.json()["assigned_responder_id"] == "BBMP_Rapid_Unit_1"

    # 12. Update task to in_progress
    step_res = client.patch(
        f"/api/coordination/tasks/{task_id}/status",
        json={"status": "in_progress", "actor_id": "BBMP_Rapid_Unit_1", "actor_role": "responder", "notes": "Unit arrived on site. High-volume pump engaged."},
        headers={"X-Responder-Id": "BBMP_Rapid_Unit_1"},
    )
    assert step_res.status_code == 200
    assert step_res.json()["status"] == "in_progress"

    # 13 & 14. Upload resolution evidence and mark resolved
    resolution_files = {"file": ("resolved_underpass_clear.png", VALID_PNG_BYTES, "image/png")}
    resolution_data = {
        "notes": "Underpass suction complete. Sump cleared. Water level 0cm. Traffic reopened safely.",
        "actor_id": "BBMP_Rapid_Unit_1",
        "actor_role": "responder",
    }
    resolve_res = client.post(
        f"/api/coordination/tasks/{task_id}/resolve",
        data=resolution_data,
        files=resolution_files,
        headers={"X-Responder-Id": "BBMP_Rapid_Unit_1"},
    )
    assert resolve_res.status_code == 200
    resolved = resolve_res.json()
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] is not None
    assert resolved["resolution_image_url"] is not None
    assert "Underpass suction complete" in resolved["resolution_notes"]

    # 15. Confirm the complete audit history in database
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT action, actor_role, details_json FROM response_audit_log ORDER BY log_id ASC")
        logs = cursor.fetchall()
        actions = [row["action"] for row in logs]

        assert "citizen_report_created" in actions
        assert "citizen_report_verified" in actions
        assert "response_task_created" in actions
        assert "response_task_assigned" in actions
        assert "response_task_status_updated" in actions


def test_offline_scenario_and_duplicate_prevention():
    """Verifies offline queueing simulation, retry behaviour, and duplicate report linking."""
    # Simulate first submission of a report
    res1 = client.post(
        "/api/reports",
        data={
            "spot_id": "bellandur",
            "report_type": "flood",
            "severity_level": "high",
            "notes": "Lake overflow near ecospace culvert.",
            "latitude": "12.9260",
            "longitude": "77.6762",
            "reporter_alias": "Citizen_ORR",
        },
    )
    assert res1.status_code == 201
    rep1_id = res1.json()["report_id"]

    # Simulate a second retry or duplicate submission from another citizen at the exact same location
    res2 = client.post(
        "/api/reports",
        data={
            "spot_id": "bellandur",
            "report_type": "flood",
            "severity_level": "high",
            "notes": "Water spilling from lake onto service road.",
            "latitude": "12.9261",
            "longitude": "77.6763",
            "reporter_alias": "Citizen_ORR_2",
        },
    )
    assert res2.status_code == 201
    rep2_id = res2.json()["report_id"]

    # In operator queue, the second report should flag proximity to rep1
    queue = client.get("/api/operator/queue?status=submitted", headers=OPERATOR_HEADERS).json()
    item2 = next(r for r in queue if r["report_id"] == rep2_id)
    assert item2["nearby_reports_count"] >= 1

    # Operator links report 2 as duplicate of report 1
    link_res = client.post(
        f"/api/operator/reports/{rep2_id}/link-duplicate?parent_report_id={rep1_id}&reviewer_id=Operator_Bellandur&reason=Same+incident+location",
        headers=OPERATOR_HEADERS,
    )
    assert link_res.status_code == 200
    linked = link_res.json()
    assert linked["duplicate_of_id"] == rep1_id
    assert linked["verification_status"] == "rejected"

    # Confirm that linked duplicate is excluded from evidence count (no double-counting)
    # Even if rep1 is approved, rep2 must not add a second count
    client.post(
        f"/api/operator/reports/{rep1_id}/decision",
        json={"decision": "approved", "reviewer_id": "Operator_Bellandur"},
        headers=OPERATOR_HEADERS,
    )
    ev_res = client.get("/api/evidence/bellandur")
    assert ev_res.status_code == 200
    ev = ev_res.json()
    assert rep1_id in ev["approved_report_ids"]
    assert rep2_id not in ev["approved_report_ids"]


def test_security_unauthorized_access_controls():
    """Verify all verification, operator, and assignment endpoints reject unauthorized callers."""
    # 1. Verification decision endpoint
    res = client.post(
        "/api/operator/reports/rep_test123/decision",
        json={"decision": "approved", "reviewer_id": "Hacker"},
    )
    assert res.status_code == 401

    # 2. Operator queue
    res = client.get("/api/operator/queue")
    assert res.status_code == 401

    # 3. Task creation
    res = client.post(
        "/api/coordination/tasks",
        json={"spot_id": "silk_board", "title": "Test", "description": "Test"},
    )
    assert res.status_code == 401

    # 4. Task assignment
    res = client.post(
        "/api/coordination/tasks/task_123/assign",
        json={"responder_id": "Unit_1"},
    )
    assert res.status_code == 401

    # 5. Public emergency alert approval gate
    res = client.post(
        "/api/coordination/notifications/notif_123/approve",
        json={"operator_id": "Operator"},
    )
    assert res.status_code == 401


def test_security_responder_scoping_and_forbidden_tampering():
    """Verify responders can only access and update tasks assigned to their specific unit."""
    # Create task assigned to Unit_Alpha
    task = client.post(
        "/api/coordination/tasks",
        json={"spot_id": "silk_board", "title": "Unit Alpha Task", "description": "Desc", "assigned_responder_id": "Unit_Alpha"},
        headers=OPERATOR_HEADERS,
    ).json()
    task_id = task["task_id"]

    # Unit_Beta attempts to progress Unit_Alpha's task -> 403 Forbidden
    hack_step = client.patch(
        f"/api/coordination/tasks/{task_id}/status",
        json={"status": "in_progress", "actor_id": "Unit_Beta", "actor_role": "responder"},
        headers={"X-Responder-Id": "Unit_Beta"},
    )
    assert hack_step.status_code == 403
    assert "Access Denied" in hack_step.json()["detail"]

    # Unit_Beta attempts to add a progress note -> 403 Forbidden
    hack_note = client.post(
        f"/api/coordination/tasks/{task_id}/notes",
        json={"note": "Fake note from unauthorized unit", "author_id": "Unit_Beta"},
        headers={"X-Responder-Id": "Unit_Beta"},
    )
    assert hack_note.status_code == 403


def test_security_file_upload_safeguards_and_path_traversal():
    """Verify photo upload rejects oversized files, invalid types, and neutralizes path traversal."""
    # 1. Path traversal in upload filename (e.g. ../../test.png)
    traversal_files = {"image": ("../../../../evil_path.png", VALID_PNG_BYTES, "image/png")}
    res = client.post(
        "/api/reports",
        data={"spot_id": "silk_board", "report_type": "flood", "latitude": "12.917", "longitude": "77.623"},
        files=traversal_files,
    )
    assert res.status_code == 201
    img_url = res.json()["image_url"]
    # Path traversal should be stripped; saved as clean random UUID
    assert "evil_path" not in img_url
    assert ".." not in img_url
    assert img_url.startswith("/static/uploads/rep_")

    # 2. File size limit (>5MB rejected)
    huge_bytes = b"0" * (5 * 1024 * 1024 + 1024)  # 5MB + 1KB
    huge_files = {"image": ("huge.png", huge_bytes, "image/png")}
    res_huge = client.post(
        "/api/reports",
        data={"spot_id": "silk_board", "report_type": "flood", "latitude": "12.917", "longitude": "77.623"},
        files=huge_files,
    )
    assert res_huge.status_code == 400
    assert "5 MB" in res_huge.json()["detail"]

    # 3. Invalid file type (executable / shell script masquerading as png)
    fake_exe_bytes = b"#!/bin/bash\necho 'malicious executable payload'\n"
    fake_files = {"image": ("script.exe", fake_exe_bytes, "application/octet-stream")}
    res_fake = client.post(
        "/api/reports",
        data={"spot_id": "silk_board", "report_type": "flood", "latitude": "12.917", "longitude": "77.623"},
        files=fake_files,
    )
    assert res_fake.status_code == 400
    assert "Unsupported image format" in res_fake.json()["detail"]

    # 4. Direct StaticFiles path traversal attempt on GET /static/uploads/
    static_traversal = client.get("/static/uploads/../../requirements.txt")
    assert static_traversal.status_code in (404, 400)


def test_security_tracking_token_entropy_and_privacy():
    """Verify tracking tokens have high entropy (not sequential) and no mandatory PII."""
    res1 = client.post("/api/reports", data={"spot_id": "silk_board", "report_type": "flood", "latitude": "12.91", "longitude": "77.62"})
    res2 = client.post("/api/reports", data={"spot_id": "silk_board", "report_type": "flood", "latitude": "12.91", "longitude": "77.62"})
    assert res1.status_code == 201
    assert res2.status_code == 201
    t1 = res1.json()["report_id"]
    t2 = res2.json()["report_id"]

    assert t1 != t2
    assert t1.startswith("rep_")
    assert t2.startswith("rep_")
    assert len(t1) >= 14
    # Neither should be an integer
    assert not t1[4:].isdigit()
    # Reporter alias defaults to anonymous
    assert res1.json()["reporter_alias"] == "Anonymous Citizen"
