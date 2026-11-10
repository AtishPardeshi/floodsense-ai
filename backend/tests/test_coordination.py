"""Automated tests for Civic Response Coordination, Deterministic Prioritization, and In-App Notifications."""
import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.coordination_service import coordination_service
from app.services.citizen_service import citizen_service

client = TestClient(app)
OPERATOR_HEADERS = {"X-Operator-Key": "bbmp-operator-secret-2026"}


def test_deterministic_prioritization_calculation():
    """Verify deterministic scoring breakdown adheres strictly to physical & verified rules."""
    # Test Silk Board (rel_depth=1.8m, surface/shallow) vs KR Circle (rel_depth=3.8m, underpass)
    kr_preview = coordination_service.calculate_task_priority(
        spot_id="kr_circle",
        override_severity=4,  # Critical
    )
    # Critical severity (40 pts) + Underpass criticality (15 pts) = >= 55 pts -> P2_HIGH or P1_CRITICAL
    assert kr_preview.total_score >= 55
    assert any(f.factor == "location_criticality" and f.points == 15 for f in kr_preview.factors)
    assert any(f.factor == "incident_severity" and f.points == 40 for f in kr_preview.factors)
    assert any("Critical underpass depression" in f.reason for f in kr_preview.factors)

    # Low severity on spot
    silk_preview = coordination_service.calculate_task_priority(
        spot_id="silk_board",
        override_severity=1,  # Low
    )
    assert any(f.factor == "location_criticality" and f.points == 15 for f in silk_preview.factors)
    assert any(f.factor == "incident_severity" and f.points == 10 for f in silk_preview.factors)


def test_priority_preview_endpoint():
    """Test the priority preview endpoint for operators."""
    res = client.get("/api/coordination/tasks/priority-preview?spot_id=kr_circle&override_severity=3")
    assert res.status_code == 200
    data = res.json()
    assert "calculated_priority" in data
    assert "total_score" in data
    assert len(data["factors"]) == 4


def test_create_task_requires_operator_authentication():
    """Verify unauthenticated task creation is strictly rejected with 401."""
    payload = {
        "spot_id": "silk_board",
        "title": "Clear drain blockage",
        "description": "Culvert blocked by storm debris.",
    }
    # No auth header
    res = client.post("/api/coordination/tasks", json=payload)
    assert res.status_code == 401

    # Invalid auth header
    res_bad = client.post(
        "/api/coordination/tasks",
        json=payload,
        headers={"X-Operator-Key": "invalid-secret"},
    )
    assert res_bad.status_code == 401


def test_create_and_query_response_task():
    """Verify operator can create a task with automated deterministic priority."""
    payload = {
        "spot_id": "kr_circle",
        "title": "Submersible Pump Deployed at Underpass",
        "description": "Clear flood waters blocking north ramp.",
    }
    res = client.post("/api/coordination/tasks", json=payload, headers=OPERATOR_HEADERS)
    assert res.status_code == 201
    task = res.json()
    assert task["task_id"].startswith("task_")
    assert task["spot_id"] == "kr_circle"
    assert task["location_name"] == "KR Circle Underpass"
    assert task["status"] == "open"
    assert task["priority"] in ("P1_CRITICAL", "P2_HIGH", "P3_MEDIUM", "P4_LOW")
    assert task["priority_reasons"] is not None
    assert len(task["priority_reasons"]["factors"]) == 4

    # Fetch task details
    get_res = client.get(f"/api/coordination/tasks/{task['task_id']}")
    assert get_res.status_code == 200
    assert get_res.json()["task_id"] == task["task_id"]


def test_operator_assigns_responder():
    """Verify operator can assign an open task to a field responder unit."""
    # Create task
    create_res = client.post(
        "/api/coordination/tasks",
        json={"spot_id": "bellandur", "title": "Lake Outflow Clearance", "description": "Clear silt build up"},
        headers=OPERATOR_HEADERS,
    )
    task_id = create_res.json()["task_id"]

    # Unauthenticated assign -> 401
    bad_assign = client.post(f"/api/coordination/tasks/{task_id}/assign", json={"responder_id": "BBMP_Unit_1"})
    assert bad_assign.status_code == 401

    # Authenticated assign
    assign_res = client.post(
        f"/api/coordination/tasks/{task_id}/assign",
        json={"responder_id": "BBMP_Unit_7", "operator_id": "Control_Desk_Officer"},
        headers=OPERATOR_HEADERS,
    )
    assert assign_res.status_code == 200
    assigned_task = assign_res.json()
    assert assigned_task["assigned_responder_id"] == "BBMP_Unit_7"
    assert assigned_task["status"] == "assigned"


def test_responder_access_control():
    """Verify responders can only update tasks assigned to their specific unit."""
    # Create and assign task to BBMP_Unit_A
    create_res = client.post(
        "/api/coordination/tasks",
        json={
            "spot_id": "silk_board",
            "title": "Deploy sandbags",
            "description": "Protect pedestrian pathway",
            "assigned_responder_id": "BBMP_Unit_A",
        },
        headers=OPERATOR_HEADERS,
    )
    task_id = create_res.json()["task_id"]

    # Unauthorized responder (BBMP_Unit_B) attempts to update status -> 403 Forbidden
    hack_res = client.patch(
        f"/api/coordination/tasks/{task_id}/status",
        json={"status": "in_progress", "actor_id": "BBMP_Unit_B", "actor_role": "responder"},
        headers={"X-Responder-Id": "BBMP_Unit_B"},
    )
    assert hack_res.status_code == 403
    assert "Access Denied" in hack_res.json()["detail"]

    # Assigned responder (BBMP_Unit_A) updates status -> 200 OK
    valid_res = client.patch(
        f"/api/coordination/tasks/{task_id}/status",
        json={"status": "in_progress", "actor_id": "BBMP_Unit_A", "actor_role": "responder"},
        headers={"X-Responder-Id": "BBMP_Unit_A"},
    )
    assert valid_res.status_code == 200
    assert valid_res.json()["status"] == "in_progress"


def test_invalid_status_transitions():
    """Verify invalid status transitions (e.g. open -> resolved directly) are rejected with 400."""
    create_res = client.post(
        "/api/coordination/tasks",
        json={"spot_id": "silk_board", "title": "Drain grating inspection", "description": "Inspect grating"},
        headers=OPERATOR_HEADERS,
    )
    task_id = create_res.json()["task_id"]
    assert create_res.json()["status"] == "open"

    # Attempt open -> resolved (skipping assigned/in_progress)
    invalid_res = client.patch(
        f"/api/coordination/tasks/{task_id}/status",
        json={"status": "resolved", "actor_id": "Operator", "actor_role": "operator"},
    )
    assert invalid_res.status_code == 400
    assert "Invalid status transition" in invalid_res.json()["detail"]


def test_task_notes_and_resolution_with_photo():
    """Verify adding notes and resolving with photographic evidence."""
    # 1. Create task assigned to Unit_Alpha
    create_res = client.post(
        "/api/coordination/tasks",
        json={
            "spot_id": "kr_circle",
            "title": "Sump Clearing",
            "description": "De-silt underpass drainage sump",
            "assigned_responder_id": "Unit_Alpha",
        },
        headers=OPERATOR_HEADERS,
    )
    task_id = create_res.json()["task_id"]

    # 2. Add progress note
    note_res = client.post(
        f"/api/coordination/tasks/{task_id}/notes",
        json={"note": "De-silting pump active. Water level dropping at 5cm/hr.", "author_id": "Unit_Alpha"},
        headers={"X-Responder-Id": "Unit_Alpha"},
    )
    assert note_res.status_code == 200
    note_data = note_res.json()
    assert note_data["note_id"] is not None
    assert "De-silting pump active" in note_data["note"]

    # 3. Transition to in_progress
    step_res = client.patch(
        f"/api/coordination/tasks/{task_id}/status",
        json={"status": "in_progress", "actor_id": "Unit_Alpha", "actor_role": "responder"},
        headers={"X-Responder-Id": "Unit_Alpha"},
    )
    assert step_res.status_code == 200

    # 4. Resolve task with completion notes and photo
    fake_photo_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    files = {"file": ("resolved_proof.png", fake_photo_bytes, "image/png")}
    form_data = {
        "notes": "Underpass completely cleared. Water table normalized. Safe for traffic.",
        "actor_id": "Unit_Alpha",
        "actor_role": "responder",
    }
    resolve_res = client.post(
        f"/api/coordination/tasks/{task_id}/resolve",
        data=form_data,
        files=files,
        headers={"X-Responder-Id": "Unit_Alpha"},
    )
    assert resolve_res.status_code == 200
    resolved = resolve_res.json()
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] is not None
    assert "Underpass completely cleared" in resolved["resolution_notes"]
    assert resolved["resolution_image_url"] is not None

    # Check that the note was recorded in task.notes
    final_task = client.get(f"/api/coordination/tasks/{task_id}").json()
    assert len(final_task["notes"]) >= 2  # Progress note + resolution note


def test_in_app_notification_lifecycle_and_approval_gate():
    """Verify local notifications and the human operator approval gate for emergency broadcasts."""
    # 1. Create a notification requiring human approval (e.g. public alert)
    notif = coordination_service.create_notification(
        title="Emergency Flash Flood Warning: K.R. Circle Underpass",
        message="Extreme waterlogging detected. Underpass impassable. Take alternate route via Cubbon Park.",
        severity="critical",
        target_audience="public_advisory",
        requires_human_approval=True,
        delivery_status="pending_approval",
    )
    assert notif.requires_human_approval is True
    assert notif.delivery_status == "pending_approval"

    # 2. Check query endpoint returns it
    list_res = client.get("/api/coordination/notifications?target_audience=public_advisory")
    assert list_res.status_code == 200
    alerts = list_res.json()
    assert any(a["notification_id"] == notif.notification_id for a in alerts)

    # 3. Unauthenticated operator approval attempt -> 401
    bad_approve = client.post(f"/api/coordination/notifications/{notif.notification_id}/approve")
    assert bad_approve.status_code == 401

    # 4. Authenticated operator approval -> 200 Delivered In-App
    good_approve = client.post(
        f"/api/coordination/notifications/{notif.notification_id}/approve",
        json={"operator_id": "Chief_Disaster_Controller_1"},
        headers=OPERATOR_HEADERS,
    )
    assert good_approve.status_code == 200
    approved_notif = good_approve.json()
    assert approved_notif["delivery_status"] == "delivered_in_app"
    assert approved_notif["approved_by"] == "Chief_Disaster_Controller_1"
    assert approved_notif["approved_at"] is not None
