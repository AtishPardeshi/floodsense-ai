"""Unit tests for PhysicalRiskModel."""
from app.database.schemas import Rainfall, Spot
from app.services.physical_risk import DEFAULT_WEIGHTS, PhysicalRiskModel


def make_spot(**kwargs) -> Spot:
    base = {
        "id": "test_spot",
        "name": "Test Location",
        "lat": 12.9200,
        "lng": 77.6200,
        "rel_depth_m": 4.0,
        "catchment_ha": 200.0,
        "drain_dist_m": 250.0,
        "past_incidents": 3,
    }
    base.update(kwargs)
    return Spot(**base)


def test_score_bounded_between_zero_and_one():
    model = PhysicalRiskModel()
    spot = make_spot()

    # Extreme rainfall
    heavy_rain = Rainfall(rain_1h_mm=150.0, rain_3h_mm=300.0, forecast_2h_mm=150.0)
    res_heavy = model.predict_spot(spot, heavy_rain)
    assert 0.0 <= res_heavy.physical_score <= 1.0
    assert res_heavy.risk_level == "red"

    # Zero rainfall
    zero_rain = Rainfall()
    res_zero = model.predict_spot(spot, zero_rain)
    assert res_zero.physical_score == 0.0
    assert res_zero.risk_level == "green"


def test_risk_categories_match_thresholds():
    model = PhysicalRiskModel()
    assert model.level_for_score(0.15) == "green"
    assert model.level_for_score(0.35) == "amber"
    assert model.level_for_score(0.64) == "amber"
    assert model.level_for_score(0.65) == "red"
    assert model.level_for_score(0.95) == "red"


def test_missing_features_handled_safely_without_silent_zero():
    model = PhysicalRiskModel()
    spot = make_spot()

    # When slope is missing (None), model re-normalizes without crashing
    res_no_slope = model.predict_spot(spot, Rainfall(rain_1h_mm=40.0), slope_pct=None)
    assert res_no_slope.physical_score > 0.0
    assert "slope_pct" in res_no_slope.data_quality["missing_features"]
    assert res_no_slope.data_quality["status"] in {"high", "partial"}

    # When slope is present
    res_with_slope = model.predict_spot(spot, Rainfall(rain_1h_mm=40.0), slope_pct=0.8)
    assert "slope_pct" not in res_with_slope.data_quality["missing_features"]


def test_contributing_factors_explainability():
    model = PhysicalRiskModel()
    spot = make_spot(rel_depth_m=5.0, past_incidents=4)
    rain = Rainfall(rain_1h_mm=45.0, rain_3h_mm=80.0)

    res = model.predict_spot(spot, rain, slope_pct=0.9)
    assert len(res.contributing_factors) >= 3
    # Check that explanatory strings exist
    assert any("intensity" in f.lower() or "rain" in f.lower() for f in res.contributing_factors)
    assert any("below" in f.lower() or "crest" in f.lower() for f in res.contributing_factors)
    assert any("past" in f.lower() or "flood" in f.lower() for f in res.contributing_factors)


def test_predictions_are_deterministic():
    model = PhysicalRiskModel()
    spot = make_spot()
    rain = Rainfall(rain_1h_mm=30.0, rain_3h_mm=50.0, forecast_2h_mm=40.0)

    res1 = model.predict_spot(spot, rain, slope_pct=1.2)
    res2 = model.predict_spot(spot, rain, slope_pct=1.2)

    assert res1.physical_score == res2.physical_score
    assert res1.risk_level == res2.risk_level
    assert res1.lead_time_min == res2.lead_time_min
    assert res1.contributing_factors == res2.contributing_factors


def test_custom_weights_configuration():
    custom_weights = {
        "depression": 0.50,
        "catchment": 0.10,
        "drain": 0.10,
        "history": 0.10,
        "slope": 0.20,
    }
    model = PhysicalRiskModel(weights=custom_weights)
    spot = make_spot(rel_depth_m=5.5)
    res = model.predict_spot(spot, Rainfall(rain_1h_mm=35.0), slope_pct=0.5)
    assert res.physical_score > 0.0

