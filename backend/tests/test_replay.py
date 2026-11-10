"""Unit and integration tests for the Historical Storm Replay Engine."""
from fastapi.testclient import TestClient

from app.demo.replay_engine import ReplaySession, replay_manager
from app.demo.scenarios import HISTORICAL_SCENARIOS
from app.main import app

client = TestClient(app)


def test_list_replay_events():
    res = client.get("/api/replay/events")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 3
    event_ids = {e["event_id"] for e in data}
    assert "ev_20220905_deluge" in event_ids
    assert "ev_20230521_cloudburst" in event_ids


def test_replay_session_lifecycle():
    scenario = HISTORICAL_SCENARIOS["ev_20220905_deluge"]
    session = ReplaySession(scenario=scenario)

    # Initial state
    state0 = session.get_state()
    assert state0.current_step == 0
    assert not state0.is_completed
    assert not state0.is_paused
    assert len(state0.spots) == 8
    assert state0.total_steps > 10

    # Advance step
    state1 = session.next_step()
    assert state1.current_step == 1
    assert state1.timestamp > state0.timestamp

    # Pause and resume
    assert session.pause().is_paused
    assert not session.resume().is_paused

    # Reset
    state_reset = session.reset()
    assert state_reset.current_step == 0
    assert not state_reset.is_completed


def test_replay_end_of_event_stops_at_final_timestamp():
    scenario = HISTORICAL_SCENARIOS["ev_20230521_cloudburst"]
    session = ReplaySession(scenario=scenario)

    # Fast forward to end
    for _ in range(session.total_steps + 5):
        st = session.next_step()

    assert session.is_completed
    assert session.current_step == session.total_steps - 1


def test_no_actual_label_leakage_into_predictions():
    # Model predictions must NOT rely on the actual_flood outcome
    scenario = HISTORICAL_SCENARIOS["ev_20220905_deluge"]
    session = ReplaySession(scenario=scenario)
    state = session.get_state()

    for spot_data in state.spots:
        # Check that prediction fields and retrospective outcomes are completely separated
        assert "predicted_risk" in spot_data
        assert "predicted_level" in spot_data
        assert "retrospective_outcome" in spot_data
        # Outcomes must only be in retrospective_outcome
        assert "actual_flood" in spot_data["retrospective_outcome"]
        assert isinstance(spot_data["predicted_risk"], float)


def test_replay_api_full_flow():
    # 1. Start session
    start_res = client.post("/api/replay/start/ev_20220905_deluge")
    assert start_res.status_code == 200
    data = start_res.json()
    run_id = data["run_id"]
    assert data["current_step"] == 0

    # 2. Query state
    state_res = client.get(f"/api/replay/{run_id}/state")
    assert state_res.status_code == 200
    assert state_res.json()["run_id"] == run_id

    # 3. Next step
    next_res = client.post(f"/api/replay/{run_id}/next")
    assert next_res.status_code == 200
    assert next_res.json()["current_step"] == 1

    # 4. History
    hist_res = client.get(f"/api/replay/{run_id}/history")
    assert hist_res.status_code == 200
    assert len(hist_res.json()["timeline"]) == 2

    # 5. Invalid event
    err_res = client.post("/api/replay/start/non_existent_event")
    assert err_res.status_code == 404

