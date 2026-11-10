from app.database.schemas import Rainfall
from app.demo.fixtures import SPOTS
from app.services.risk_engine import level_for, score_all, score_spot

BY_ID = {s.id: s for s in SPOTS}


def test_dry_weather_is_green_everywhere():
    assert all(r.level == "green" for r in score_all(SPOTS, Rainfall()))


def test_heavy_rain_hits_vulnerable_spot_hardest():
    rain = Rainfall(rain_1h_mm=45, rain_3h_mm=90, forecast_2h_mm=80)
    results = score_all(SPOTS, rain)
    assert results[0].spot_id in {"bellandur", "silk_board"}
    assert results[0].level == "red"
    assert score_spot(BY_ID["indiranagar"], rain).risk < results[0].risk


def test_risk_never_decreases_with_more_rain():
    spot = BY_ID["silk_board"]
    last = -1.0
    for mm in range(0, 80, 5):
        r = score_spot(spot, Rainfall(rain_1h_mm=mm, rain_3h_mm=mm * 2, forecast_2h_mm=mm * 2)).risk
        assert r >= last
        last = r


def test_forecast_gives_lead_time():
    spot = BY_ID["silk_board"]
    r = score_spot(spot, Rainfall(rain_1h_mm=5, rain_3h_mm=10, forecast_2h_mm=110))
    assert r.lead_time_min == 45


def test_level_thresholds():
    assert level_for(0.2) == "green"
    assert level_for(0.5) == "amber"
    assert level_for(0.8) == "red"


def test_fixtures_past_incidents_reconciled_with_incident_ledger():
    """Ensures past_incidents in SPOTS matches the verified incident records exactly."""
    assert BY_ID["silk_board"].past_incidents == 2
    assert BY_ID["bellandur"].past_incidents == 2
    assert BY_ID["kr_circle"].past_incidents == 2
    assert BY_ID["agara"].past_incidents == 2
    assert BY_ID["hebbal"].past_incidents == 2
    assert BY_ID["mahadevapura"].past_incidents == 2
    assert BY_ID["hsr_layout"].past_incidents == 1
    assert BY_ID["indiranagar"].past_incidents == 1
    total_incidents = sum(s.past_incidents for s in SPOTS)
    assert total_incidents == 14
