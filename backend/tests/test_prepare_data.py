import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_data import build_labels, load_raw_rainfall, process_rainfall, year_chunks  # noqa: E402


def make_frame() -> pd.DataFrame:
    """20 dry days with one storm: 8, 30, 12 mm in the hours 14:00, 15:00, 16:00 on 10 June."""
    ts = pd.date_range("2024-06-01", "2024-06-20 23:00", freq="h")
    p = pd.Series(0.0, index=range(len(ts)))
    i = list(ts).index(pd.Timestamp("2024-06-10 15:00"))
    p[i - 1], p[i], p[i + 1] = 8, 30, 12
    return process_rainfall(pd.DataFrame({"timestamp": ts, "precip_mm": p}))


def make_frame_two_storms() -> pd.DataFrame:
    """Frame with two storms: June 10 (storm 1, flood) and June 15 (storm 2, non-flood rain)."""
    ts = pd.date_range("2024-06-01", "2024-06-20 23:00", freq="h")
    p = pd.Series(0.0, index=range(len(ts)))
    i1 = list(ts).index(pd.Timestamp("2024-06-10 15:00"))
    p[i1 - 1], p[i1], p[i1 + 1] = 8, 30, 12
    i2 = list(ts).index(pd.Timestamp("2024-06-15 15:00"))
    p[i2 - 1], p[i2], p[i2 + 1] = 10, 25, 15
    return process_rainfall(pd.DataFrame({"timestamp": ts, "precip_mm": p}))


def incidents(**row) -> pd.DataFrame:
    base = {"incident_id": "i1", "spot_id": "a", "date": "2024-06-10", "start_time_local": ""}
    return pd.DataFrame([{**base, **row}])


def test_rolling_features():
    df = make_frame()
    at = lambda t: df[df.timestamp == t].iloc[0]  # noqa: E731
    assert at("2024-06-10 15:00").rain_1h_mm == 30
    assert at("2024-06-10 15:00").rain_3h_mm == 38      # 0 + 8 + 30 (past hours only)
    assert at("2024-06-10 14:00").next_2h_mm == 42      # 30 + 12 (future hours)


def test_rolling_6h_and_24h_features():
    df = make_frame()
    at = lambda t: df[df.timestamp == t].iloc[0]  # noqa: E731
    # At 16:00, past 6h includes 8, 30, 12 = 50 mm
    assert at("2024-06-10 16:00").rain_6h_mm == 50
    assert at("2024-06-10 16:00").rain_24h_mm == 50


def test_time_given_labels_that_hour_window():
    labels, skipped = build_labels({"a": make_frame()}, incidents(start_time_local="15:20"))
    assert not skipped
    flood = labels[labels.flood == 1]
    assert list(flood.timestamp) == list(pd.to_datetime(["2024-06-10 14:00", "2024-06-10 15:00", "2024-06-10 16:00"]))
    assert set(flood.label_basis) == {"time_given"}


def test_missing_time_uses_peak_rain_and_says_so():
    labels, _ = build_labels({"a": make_frame()}, incidents())
    flood = labels[labels.flood == 1]
    assert pd.Timestamp("2024-06-10 15:00") in set(flood.timestamp)
    assert set(flood.label_basis) == {"peak_rain_assumed"}


def test_dry_day_incident_is_skipped_not_labelled():
    labels, skipped = build_labels({"a": make_frame()}, incidents(date="2024-06-03"))
    assert labels.flood.sum() == 0
    assert skipped and "no rain" in skipped[0][1]


def test_unknown_spot_and_out_of_range_are_reported():
    _, s1 = build_labels({"a": make_frame()}, incidents(spot_id="zzz"))
    _, s2 = build_labels({"a": make_frame()}, incidents(date="2023-01-01"))
    assert "unknown spot_id" in s1[0][1]
    assert "outside" in s2[0][1]


def test_negatives_are_rainy_and_not_next_to_floods():
    labels, _ = build_labels({"a": make_frame_two_storms()}, incidents(start_time_local="15:00"))
    neg = labels[labels.flood == 0]
    # window 14-16 on June 10 labelled flood, hours 11-13 and 17-19 excluded as ambiguous
    near = pd.to_datetime([f"2024-06-10 {h}:00" for h in (11, 12, 13, 17, 18, 19)])
    assert not set(near) & set(neg.timestamp)
    assert len(neg) > 0
    assert (neg.rain_3h_mm >= 5).all()


def test_year_chunks_split_on_year_boundaries():
    assert year_chunks(date(2023, 5, 1), date(2024, 3, 31)) == [
        ("2023-05-01", "2023-12-31"),
        ("2024-01-01", "2024-03-31"),
    ]


def test_missing_timestamp_gaps_are_filled():
    ts = pd.to_datetime(["2024-06-10 10:00", "2024-06-10 11:00", "2024-06-10 14:00"])
    raw_df = pd.DataFrame({"timestamp": ts, "precip_mm": [5.0, 10.0, 15.0]})
    proc = process_rainfall(raw_df)
    assert len(proc) == 5  # 10:00, 11:00, 12:00, 13:00, 14:00
    at = lambda t: proc[proc.timestamp == t].iloc[0]  # noqa: E731
    assert at("2024-06-10 12:00").rain_1h_mm == 0.0
    assert at("2024-06-10 13:00").rain_1h_mm == 0.0


def test_strict_negatives_marks_unassessed_as_unknown():
    # In strict_negatives mode, rainy hours without verified non-flood assessment are -1 (unknown)
    labels, _ = build_labels({"a": make_frame_two_storms()}, incidents(start_time_local="15:00"), strict_negatives=True)
    assert (labels.flood == 1).sum() > 0
    # Any unassessed rainy candidate is marked -1
    unknowns = labels[labels.flood == -1]
    assert len(unknowns) > 0
    assert (unknowns.rain_3h_mm >= 5).all()
    assert (unknowns.label_rule == "unassessed_rainy_context").all()


def test_verified_control_generates_zero_label():
    inc_df = pd.DataFrame([
        {"incident_id": "i1", "spot_id": "a", "date": "2024-06-10", "start_time_local": "15:00", "severity": "2"},
        {"incident_id": "ctrl1", "spot_id": "a", "date": "2024-06-15", "start_time_local": "15:00", "severity": "0", "source_type": "control_observation"},
    ])
    labels, _ = build_labels({"a": make_frame_two_storms()}, inc_df, strict_negatives=True)
    control_rows = labels[labels.flood == 0]
    assert len(control_rows) > 0
    assert (control_rows.label_rule == "verified_control_non_flood").all()


def test_duplicate_incidents_handled():
    inc_df = pd.DataFrame([
        {"incident_id": "i1", "spot_id": "a", "date": "2024-06-10", "start_time_local": "15:00"},
        {"incident_id": "i1", "spot_id": "a", "date": "2024-06-10", "start_time_local": "15:00"},
    ])
    labels, _ = build_labels({"a": make_frame()}, inc_df)
    assert (labels.flood == 1).sum() == 3  # 14:00, 15:00, 16:00 only


def test_offline_rainfall_loading_from_cache(tmp_path: Path):
    cache_file = tmp_path / "spot1_2024-06-01_2024-06-02.json"
    dummy_data = {
        "hourly": {
            "time": ["2024-06-01T00:00", "2024-06-01T01:00"],
            "precipitation": [0.0, 12.5],
        }
    }
    cache_file.write_text(json.dumps(dummy_data))
    spot_series = pd.Series({"spot_id": "spot1", "lat": 12.9, "lng": 77.6})
    chunks = [("2024-06-01", "2024-06-02")]
    df = load_raw_rainfall(spot_series, chunks, raw_dir=tmp_path, refresh=False)
    assert len(df) == 2
    assert df.iloc[1].precip_mm == 12.5
