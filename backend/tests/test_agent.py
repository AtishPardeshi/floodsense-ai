"""Unit and integration tests for AI Early-Warning Agent."""
from fastapi.testclient import TestClient

from app.database.schemas import Level, SpotRisk
from app.main import app
from app.services.agent_service import early_warning_agent

client = TestClient(app)


def test_agent_advisory_routine_green_scenario():
    spots = [
        {"spot_id": "silk_board", "name": "Silk Board Junction", "level": "green", "risk": 0.10, "lead_time_min": None, "drivers": []},
        {"spot_id": "kr_circle", "name": "KR Circle Underpass", "level": "green", "risk": 0.05, "lead_time_min": None, "drivers": []},
    ]
    advisory = early_warning_agent.generate_advisory(spots)
    assert advisory.overall_alert_level == "green"
    assert "ಸಾಮಾನ್ಯ ಸ್ಥಿತಿ" in advisory.citizen_advisory.kannada
    assert len(advisory.municipal_action_plan.pump_deployments) == 0


def test_agent_advisory_emergency_red_scenario():
    spots = [
        {"spot_id": "kr_circle", "name": "KR Circle Underpass", "level": "red", "risk": 0.85, "lead_time_min": 45, "drivers": ["Heavy rain"]},
        {"spot_id": "bellandur", "name": "Bellandur Lake Edge", "level": "red", "risk": 0.78, "lead_time_min": 0, "drivers": ["Lake overflow"]},
    ]
    advisory = early_warning_agent.generate_advisory(spots)
    assert advisory.overall_alert_level == "red"
    assert advisory.high_risk_spots_count == 2
    # Bilingual checks
    assert "FLASH FLOOD WARNING" in advisory.citizen_advisory.english
    assert "ತುರ್ತು ಪ್ರವಾಹ ಎಚ್ಚರಿಕೆ" in advisory.citizen_advisory.kannada
    # Municipal pump deployments
    assert len(advisory.municipal_action_plan.pump_deployments) == 2
    assert any("KR Circle" in p["location"] for p in advisory.municipal_action_plan.pump_deployments)
    # Underpass barricade order
    assert len(advisory.municipal_action_plan.barricade_orders) >= 1


def test_agent_api_endpoints():
    # POST /api/agent/advisory with custom spots
    payload = [
        {"spot_id": "agara", "name": "Agara Underpass", "level": "amber", "risk": 0.45, "lead_time_min": 45, "drivers": ["Deep depression"]}
    ]
    res = client.post("/api/agent/advisory", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["overall_alert_level"] == "amber"
    assert "citizen_advisory" in data
    assert "kannada" in data["citizen_advisory"]
    assert "municipal_action_plan" in data

    # GET /api/agent/advisory/live
    live_res = client.get("/api/agent/advisory/live")
    assert live_res.status_code == 200
    live_data = live_res.json()
    assert live_data["overall_alert_level"] in {"green", "amber", "red"}

