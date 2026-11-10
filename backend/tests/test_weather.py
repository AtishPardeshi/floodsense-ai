"""Unit and integration tests for WeatherService."""
from fastapi.testclient import TestClient

from app.main import app
from app.services.weather_service import WeatherService, weather_service

client = TestClient(app)


def test_weather_summary_structure():
    summary = weather_service.get_live_weather()
    assert summary.timestamp is not None
    assert len(summary.spots_weather) == 8
    assert summary.bengaluru_avg_rain_1h >= 0.0
    assert summary.data_source is not None


def test_weather_caching_within_ttl():
    svc = WeatherService()
    res1 = svc.get_live_weather()
    # Immediate second call should use cache
    res2 = svc.get_live_weather(force_refresh=False)
    assert res1.timestamp == res2.timestamp


def test_weather_api_endpoints():
    live_res = client.get("/api/weather/live")
    assert live_res.status_code == 200
    data = live_res.json()
    assert "spots_weather" in data
    assert len(data["spots_weather"]) == 8

    risk_res = client.get("/api/weather/risk")
    assert risk_res.status_code == 200
    risks = risk_res.json()
    assert len(risks) == 8
    assert {"spot_id", "risk", "level", "drivers"} <= set(risks[0].keys())

