"""Tests for Citizen Intelligence Reporting, PWA API, and Verification Workflow."""
import io
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_report_json():
    """Test standard citizen flood report submission via JSON."""
    payload = {
        "spot_id": "silk_board",
        "report_type": "flood",
        "water_depth_cm": 45.0,
        "severity_level": "high",
        "reporter_alias": "Citizen Ramesh",
        "notes": "Water up to knee level near the service road.",
    }
    response = client.post("/api/reports", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["report_id"].startswith("rep_")
    assert data["spot_id"] == "silk_board"
    assert data["spot_name"] == "Silk Board Junction"
    assert data["report_type"] == "flood"
    assert data["water_depth_cm"] == 45.0
    assert data["severity"] == 3
    assert data["severity_level"] == "high"
    assert data["verification_status"] == "submitted"  # Not verified yet!


def test_create_report_control_clear():
    """Test citizen reporting passable/clear road (negative ground-truth control)."""
    payload = {
        "spot_id": "indiranagar",
        "report_type": "control_clear",
        "reporter_alias": "Cyclist Priya",
        "notes": "100ft road is completely clear, drains flowing smoothly.",
    }
    response = client.post("/api/reports", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["report_type"] == "control_clear"
    assert data["severity"] is None
    assert data["verification_status"] == "submitted"


def test_create_report_with_photo():
    """Test report creation with multipart form and image attachment."""
    # Create valid 1x1 PNG bytes
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    files = {"image": ("flood_photo.png", io.BytesIO(fake_png), "image/png")}
    form_data = {
        "spot_id": "bellandur",
        "report_type": "flood",
        "water_depth_cm": "65",
        "severity_level": "critical",
        "notes": "Severe water accumulation near tech park gate.",
    }
    response = client.post("/api/reports", data=form_data, files=files)
    assert response.status_code == 201
    data = response.json()
    assert data["image_url"] is not None
    assert data["image_url"].startswith("/static/uploads/rep_")
    assert data["severity"] == 4
    assert data["severity_level"] == "critical"


def test_create_report_rejects_oversized_photo():
    """Test that uploaded image exceeding 5MB is rejected with 400."""
    oversized = b"\xff\xd8\xff" + b"0" * (5 * 1024 * 1024 + 100)
    files = {"image": ("huge_photo.jpg", io.BytesIO(oversized), "image/jpeg")}
    form_data = {"spot_id": "silk_board"}
    response = client.post("/api/reports", data=form_data, files=files)
    assert response.status_code == 400
    assert "exceeds maximum allowable limit" in response.json()["detail"]


def test_create_report_gps_nearest_spot():
    """Test submitting report with GPS coordinates matching the nearest monitored spot."""
    # Silk Board is at 12.9177, 77.6233
    payload = {
        "latitude": 12.9180,
        "longitude": 77.6230,
        "report_type": "flood",
        "notes": "GPS pin placed by citizen on phone",
    }
    response = client.post("/api/reports", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["spot_id"] == "silk_board"
    assert "Silk Board" in data["spot_name"]
    assert data["latitude"] == 12.9180
    assert data["longitude"] == 77.6230


def test_get_report_by_tracking_id():
    """Test retrieving report by tracking ID and 404 for unknown tokens."""
    payload = {"spot_id": "kr_circle", "notes": "Tracking verification test"}
    create_res = client.post("/api/reports", json=payload)
    report_id = create_res.json()["report_id"]

    fetch_res = client.get(f"/api/reports/{report_id}")
    assert fetch_res.status_code == 200
    assert fetch_res.json()["report_id"] == report_id
    assert fetch_res.json()["verification_status"] == "submitted"

    notFound_res = client.get("/api/reports/rep_nonexistent999")
    assert notFound_res.status_code == 404


def test_operator_verification_requires_authentication():
    """Test that verification endpoints reject unauthenticated requests with 401."""
    create_res = client.post("/api/reports", json={"spot_id": "silk_board", "notes": "Test auth"})
    report_id = create_res.json()["report_id"]

    # No key provided -> 401
    unauth_res = client.post(
        f"/api/reports/{report_id}/verify",
        json={"action": "approved", "operator_id": "Hacker", "notes": "Fake approve"},
    )
    assert unauth_res.status_code == 401

    # Wrong key provided -> 401
    bad_key_res = client.post(
        f"/api/reports/{report_id}/verify",
        json={"action": "approved", "operator_id": "Hacker", "notes": "Fake approve"},
        headers={"X-Operator-Key": "wrong-secret-key"},
    )
    assert bad_key_res.status_code == 401


def test_operator_verification_workflow():
    """Test full municipal operator lifecycle: submitted -> under_review -> approved."""
    create_res = client.post("/api/reports", json={"spot_id": "agara", "notes": "Underpass blocked"})
    report_id = create_res.json()["report_id"]

    headers = {"X-Operator-Key": "bbmp-operator-secret-2026"}

    # Step 1: Under review
    rev_res = client.post(
        f"/api/reports/{report_id}/verify",
        json={"action": "under_review", "operator_id": "BBMP_Traffic_Cell", "notes": "Reviewing CCTV feed"},
        headers=headers,
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["verification_status"] == "under_review"

    # Step 2: Approved
    app_res = client.post(
        f"/api/reports/{report_id}/verify",
        json={"action": "approved", "operator_id": "BBMP_Traffic_Cell", "notes": "Confirmed on CCTV camera 14"},
        headers=headers,
    )
    assert app_res.status_code == 200
    assert app_res.json()["verification_status"] == "approved"
    assert "Confirmed on CCTV" in app_res.json()["notes"]

