"""API endpoints for Historical Storm Replay."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException

from app.demo.replay_engine import replay_manager

router = APIRouter(prefix="/replay", tags=["replay"])


@router.get("/events")
def list_replay_events() -> list[dict[str, Any]]:
    """Lists all documented historical storms available for simulation replay."""
    return replay_manager.list_available_events()


@router.post("/start/{event_id}")
def start_replay(event_id: str) -> dict[str, Any]:
    """Initializes a new chronological storm replay session."""
    try:
        session = replay_manager.start_session(event_id)
        return session.get_state().to_dict()
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize replay: {e}")


@router.get("/{run_id}/state")
def get_replay_state(run_id: str) -> dict[str, Any]:
    """Returns the current step state of the specified replay session."""
    try:
        session = replay_manager.get_session(run_id)
        return session.get_state().to_dict()
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{run_id}/next")
def next_step(run_id: str) -> dict[str, Any]:
    """Advances replay by one hourly timestep."""
    try:
        session = replay_manager.get_session(run_id)
        return session.next_step().to_dict()
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{run_id}/pause")
def pause_replay(run_id: str) -> dict[str, Any]:
    """Pauses the replay session."""
    try:
        session = replay_manager.get_session(run_id)
        return session.pause().to_dict()
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{run_id}/resume")
def resume_replay(run_id: str) -> dict[str, Any]:
    """Resumes the replay session."""
    try:
        session = replay_manager.get_session(run_id)
        return session.resume().to_dict()
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{run_id}/reset")
def reset_replay(run_id: str) -> dict[str, Any]:
    """Resets the replay session to its initial timestep."""
    try:
        session = replay_manager.get_session(run_id)
        return session.reset().to_dict()
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{run_id}/history")
def get_replay_history(run_id: str) -> dict[str, Any]:
    """Returns the chronological timeline history up to the current timestep."""
    try:
        session = replay_manager.get_session(run_id)
        current_state = session.get_state()
        return {
            "run_id": run_id,
            "event_id": session.scenario.event_id,
            "scenario_name": session.scenario.name,
            "current_step": session.current_step,
            "total_steps": len(session.timeline),
            "timeline": [t.isoformat() for t in session.timeline[: session.current_step + 1]],
            "latest_state": current_state.to_dict(),
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

