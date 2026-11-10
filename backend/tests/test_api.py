from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_risk_endpoint_shape():
    res = client.get("/api/risk", params={"rain_1h_mm": 40, "rain_3h_mm": 80, "forecast_2h_mm": 60})
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 8
    assert {"spot_id", "risk", "level", "lead_time_min", "drivers"} <= set(data[0])
    assert data == sorted(data, key=lambda r: r["risk"], reverse=True)


def test_risk_rejects_negative_rain():
    assert client.get("/api/risk", params={"rain_1h_mm": -1}).status_code == 422
