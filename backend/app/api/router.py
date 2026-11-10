from fastapi import APIRouter

from app.api.endpoints import agent, coordination, dispatch, evidence, health, operator, replay, reports, risk, weather

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(risk.router)
api_router.include_router(replay.router)
api_router.include_router(weather.router)
api_router.include_router(agent.router)
api_router.include_router(reports.router)
api_router.include_router(operator.router)
api_router.include_router(evidence.router)
api_router.include_router(dispatch.router)
api_router.include_router(coordination.router)
