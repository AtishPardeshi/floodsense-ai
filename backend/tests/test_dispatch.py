"""Automated tests for Municipal Dewatering & Barricade Dispatch Management."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
OPERATOR_HEADERS = {"X-Operator-Key": "bbmp-operator-secret-2026"}


def test_dispatch_endpoints_require_operator_authentication():
    """Verify that dispatch endpoints reject unauthenticated calls with 401."""
    payload = {
        "spot_id": "silk_board",
        "directive_type": "pump_deployment",
        "priority": "P1_CRITICAL",
        "action_instructions": "Deploy pump",
    }

    # No auth header -> 401
    res = client.post("/api/dispatch/orders", json=payload)
    assert res.status_code == 401

    # Wrong auth header -> 401
    bad_res = client.post("/api/dispatch/orders", json=payload, headers={"X-Operator-Key": "wrong"})
    assert bad_res.status_code == 401


def test_create_dewatering_pump_dispatch():
    """Test issuing a dewatering pump deployment order."""
    payload = {
        "spot_id": "bellandur",
        "directive_type": "pump_deployment",
        "priority": "P1_CRITICAL",
        "capacity_gpm": "1000 GPM High-Volume Diesel",
        "assigned_team": "BBMP Stormwater Rapid Response Team 3",
        "action_instructions": "Deploy high-volume suction pump at Bellandur Lake outflow culvert.",
    }

    res = client.post("/api/dispatch/orders", json=payload, headers=OPERATOR_HEADERS)
    assert res.status_code == 201
    data = res.json()
    assert data["dispatch_id"].startswith("disp_")
    assert data["spot_id"] == "bellandur"
    assert data["location_name"] == "Bellandur Lake Edge"
    assert data["directive_type"] == "pump_deployment"
    assert data["status"] == "ordered"
    assert data["capacity_gpm"] == "1000 GPM High-Volume Diesel"


def test_create_barricade_and_diversion_dispatch():
    """Test issuing traffic barricade and diversion order."""
    payload = {
        "spot_id": "kr_circle",
        "directive_type": "barricade_order",
        "priority": "P1_CRITICAL",
        "assigned_team": "Bengaluru Traffic Police Ward 10",
        "action_instructions": "Place physical barricades at northern underpass approach ramp.",
    }

    res = client.post("/api/dispatch/orders", json=payload, headers=OPERATOR_HEADERS)
    assert res.status_code == 201
    data = res.json()
    assert data["directive_type"] == "barricade_order"
    assert data["location_name"] == "KR Circle Underpass"


def test_dispatch_status_transition_lifecycle():
    """Test operational status lifecycle: ordered -> en_route -> active -> demobilized."""
    # 1. Create order
    payload = {
        "spot_id": "agara",
        "directive_type": "pump_deployment",
        "priority": "P2_ELEVATED",
        "action_instructions": "Clear underpass sump",
    }
    create_res = client.post("/api/dispatch/orders", json=payload, headers=OPERATOR_HEADERS)
    dispatch_id = create_res.json()["dispatch_id"]
    assert create_res.json()["status"] == "ordered"

    # 2. Update to en_route
    r1 = client.patch(
        f"/api/dispatch/orders/{dispatch_id}/status",
        json={"status": "en_route", "operator_id": "BBMP_Dispatcher_1"},
        headers=OPERATOR_HEADERS,
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "en_route"

    # 3. Update to active
    r2 = client.patch(
        f"/api/dispatch/orders/{dispatch_id}/status",
        json={"status": "active", "operator_id": "BBMP_Field_Lead"},
        headers=OPERATOR_HEADERS,
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "active"

    # 4. Update to demobilized
    r3 = client.patch(
        f"/api/dispatch/orders/{dispatch_id}/status",
        json={"status": "demobilized", "operator_id": "BBMP_Dispatcher_1"},
        headers=OPERATOR_HEADERS,
    )
    assert r3.status_code == 200
    assert r3.json()["status"] == "demobilized"


def test_list_dispatches_with_filtering():
    """Test listing dispatches with status and spot_id filters."""
    # Create distinct order
    client.post(
        "/api/dispatch/orders",
        json={
            "spot_id": "hsr_layout",
            "directive_type": "traffic_diversion",
            "priority": "P2_ELEVATED",
            "action_instructions": "Divert traffic along 14th Main",
        },
        headers=OPERATOR_HEADERS,
    )

    # Filter by spot
    res_spot = client.get("/api/dispatch/orders?spot_id=hsr_layout", headers=OPERATOR_HEADERS)
    assert res_spot.status_code == 200
    items = res_spot.json()
    assert len(items) >= 1
    assert all(item["spot_id"] == "hsr_layout" for item in items)

    # Filter by status
    res_status = client.get("/api/dispatch/orders?status=ordered", headers=OPERATOR_HEADERS)
    assert res_status.status_code == 200
    ordered_items = res_status.json()
    assert all(item["status"] == "ordered" for item in ordered_items)

