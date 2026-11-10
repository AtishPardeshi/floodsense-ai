#!/usr/bin/env python3
"""Fetch hourly historical rainfall and build flood labels.

Run from the repo root:

    python backend/scripts/prepare_data.py
    python backend/scripts/prepare_data.py --start 2022-01-01 --end 2024-12-31

Inputs : data/raw/spots.csv, data/raw/incidents.csv
Outputs: data/raw/rainfall/*.json            (cached API responses, never re-fetched)
         data/processed/rainfall/<spot>.csv  (rolling rainfall features per spot)
         data/processed/features.csv         (combined multi-spot feature matrix)
         data/processed/labels.csv           (spot-hour rows, flood = 1/0/-1)
         data/manifests/dataset_manifest.json (dates, fetch date, checksums)

Honest limits (also stated in docs/DATA_SOURCES.md):
  * Rainfall is modelled reanalysis at a grid point, not a rain-gauge reading.
  * `next_2h_mm` is OBSERVED rain standing in for a forecast, so any lead time
    measured with it assumes a perfect forecast. Treat it as an upper bound.
  * Incidents with no clock time are labelled at that day's peak-rain hour
    (label_basis = peak_rain_assumed). Prefer incidents that give a time.
  * Labels use 3 states: 1 (documented flood), 0 (verified non-flood), -1 (unknown).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

API = "https://archive-api.open-meteo.com/v1/archive"
TZ = "Asia/Kolkata"
ARCHIVE_LAG_DAYS = 5          # the archive trails real time by a few days
POS_HALF_WINDOW_H = 1         # flood hours = report hour +/- this many hours
EXCLUDE_H = 3                 # drop ambiguous hours just outside a flood window
RAIN_CONTEXT_MM = 5.0         # candidate sampling threshold (3 h rain >= 5mm)
ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- fetching ---
def fetch_chunk(lat: float, lng: float, start: str, end: str, retries: int = 3) -> dict[str, Any]:
    params = urllib.parse.urlencode({
        "latitude": lat, "longitude": lng,
        "start_date": start, "end_date": end,
        "hourly": "precipitation", "timezone": TZ,
    })
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(f"{API}?{params}", headers={"User-Agent": "FloodSenseAI/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            if "hourly" not in data:
                raise RuntimeError(f"Unexpected response format: {str(data)[:200]}")
            return data
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(2 * attempt)
    raise RuntimeError(
        f"Could not fetch rainfall for ({lat}, {lng}) {start}..{end} after {retries} tries: {last_err}. "
        "Check your internet connection or Open-Meteo status/rate limits, then re-run: "
        "finished chunks are cached and will be skipped."
    )


def year_chunks(start: date, end: date) -> list[tuple[str, str]]:
    out = []
    for year in range(start.year, end.year + 1):
        s = max(start, date(year, 1, 1))
        e = min(end, date(year, 12, 31))
        out.append((s.isoformat(), e.isoformat()))
    return out


def load_raw_rainfall(spot: pd.Series, chunks: list[tuple[str, str]], raw_dir: Path, refresh: bool) -> pd.DataFrame:
    frames = []
    for s, e in chunks:
        path = raw_dir / f"{spot.spot_id}_{s}_{e}.json"
        if path.exists() and not refresh:
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = fetch_chunk(float(spot.lat), float(spot.lng), s, e)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            time.sleep(1)  # be polite to public API
        h = data["hourly"]
        ts = pd.to_datetime(h["time"])
        frames.append(pd.DataFrame({"timestamp": ts, "precip_mm": h["precipitation"]}))
    return pd.concat(frames, ignore_index=True)


# -------------------------------------------------------------- processing ---
def process_rainfall(raw: pd.DataFrame, freq: str = "h") -> pd.DataFrame:
    """Hourly precipitation -> rolling accumulation features with timezone and gap handling."""
    df = raw.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)

    # Ensure consistent datetime index and handle missing timestamp gaps
    if len(df) > 1:
        full_idx = pd.date_range(start=df["timestamp"].min(), end=df["timestamp"].max(), freq=freq)
        if len(full_idx) > len(df):
            gap_count = len(full_idx) - len(df)
            print(f"    note: filled {gap_count} missing hourly timestamp gaps with 0.0 mm")
            df = df.set_index("timestamp").reindex(full_idx).rename_axis("timestamp").reset_index()

    missing = int(df["precip_mm"].isna().sum())
    if missing:
        print(f"    note: {missing} missing hourly precipitation values treated as 0.0 mm")
    p = df["precip_mm"].fillna(0.0).astype(float)

    # Accumulation features (mm)
    df["rain_1h_mm"] = p
    df["rain_3h_mm"] = p.rolling(3, min_periods=1).sum()
    df["rain_6h_mm"] = p.rolling(6, min_periods=1).sum()
    df["rain_24h_mm"] = p.rolling(24, min_periods=1).sum()
    # 2-hour future lookahead (retrospective forecast proxy only; NOT available at real-time inference)
    df["next_2h_mm"] = p.shift(-1).fillna(0.0) + p.shift(-2).fillna(0.0)

    return df[["timestamp", "rain_1h_mm", "rain_3h_mm", "rain_6h_mm", "rain_24h_mm", "next_2h_mm"]]


def normalize_incident_time(inc: Any) -> tuple[str, str, str]:
    """Extracts date, time_str, and precision from incident record."""
    dt_raw = getattr(inc, "datetime", None)
    if dt_raw and not pd.isna(dt_raw) and str(dt_raw).strip():
        dt_str = str(dt_raw).strip()
        if "T" in dt_str:
            d_part, t_part = dt_str.split("T", 1)
            t_part = t_part.split("+")[0].split("-")[0][:5]
            prec = getattr(inc, "time_precision", "minute")
            return d_part, t_part, prec
        return dt_str[:10], "", "day"

    # Legacy schema fallback
    d = str(getattr(inc, "date", "")).strip()
    t = getattr(inc, "start_time_local", "")
    t_str = "" if pd.isna(t) else str(t).strip()
    prec = "minute" if t_str else "day"
    return d, t_str, prec


def build_labels(
    frames: dict[str, pd.DataFrame],
    incidents: pd.DataFrame,
    strict_negatives: bool = False,
):
    """Builds spot-hour labels.

    Returns (labels_df, skipped) where:
      flood = 1  : documented flood
      flood = 0  : verified non-flood / candidate rainy non-flood
      flood = -1 : unknown / unassessed rainy context (when strict_negatives=True)
    """
    positives: dict[str, dict[pd.Timestamp, dict[str, Any]]] = {}
    verified_controls: dict[str, set[pd.Timestamp]] = {}
    skipped: list[tuple[str, str]] = []

    # Deduplicate incidents by incident_id
    incidents_clean = incidents.drop_duplicates(subset=["incident_id"]) if "incident_id" in incidents.columns else incidents

    for inc in incidents_clean.itertuples():
        spot_id = getattr(inc, "spot_id", "")
        df = frames.get(spot_id)
        if df is None:
            skipped.append((getattr(inc, "incident_id", "unknown"), f"unknown spot_id '{spot_id}'"))
            continue

        d_str, t_str, prec = normalize_incident_time(inc)
        if not d_str:
            skipped.append((getattr(inc, "incident_id", "unknown"), "missing date"))
            continue

        day = pd.Timestamp(d_str).normalize()
        day_df = df[(df.timestamp >= day) & (df.timestamp < day + pd.Timedelta(days=1))]
        if day_df.empty:
            skipped.append((getattr(inc, "incident_id", "unknown"), "date outside the fetched rainfall range"))
            continue

        # Check for verified negative / control observation row
        sev = str(getattr(inc, "severity", "")).strip()
        src_type = str(getattr(inc, "source_type", "")).strip()
        if sev == "0" or src_type == "control_observation":
            if t_str:
                ctrl_t = pd.Timestamp(f"{d_str} {t_str}").floor("h")
                verified_controls.setdefault(spot_id, set()).add(ctrl_t)
            else:
                for t_val in day_df.timestamp:
                    verified_controls.setdefault(spot_id, set()).add(t_val)
            continue

        if t_str:
            centre = pd.Timestamp(f"{d_str} {t_str}").floor("h")
            basis = "time_given"
        else:
            if day_df.rain_1h_mm.max() <= 0:
                skipped.append((getattr(inc, "incident_id", "unknown"), "no rain recorded that day: check date or location"))
                continue
            centre = day_df.loc[day_df.rain_1h_mm.idxmax(), "timestamp"]
            basis = "peak_rain_assumed"

        spot_pos = positives.setdefault(spot_id, {})
        for k in range(-POS_HALF_WINDOW_H, POS_HALF_WINDOW_H + 1):
            target_ts = centre + pd.Timedelta(hours=k)
            spot_pos[target_ts] = {
                "incident_id": getattr(inc, "incident_id", ""),
                "basis": basis,
                "confidence": getattr(inc, "label_confidence", "high"),
                "time_precision": prec,
            }

    parts = []
    for spot_id, df in frames.items():
        pos = positives.get(spot_id, {})
        pos_ts = set(pos)
        ctrl_ts = verified_controls.get(spot_id, set())

        # Exclude +/- EXCLUDE_H hours around flood windows from negative consideration
        excluded = {t + pd.Timedelta(hours=k) for t in pos_ts for k in range(-EXCLUDE_H, EXCLUDE_H + 1)} - pos_ts

        # Candidate sampling: rainy context hours, positive flood hours, or verified control observations
        keep = df[(df.rain_3h_mm >= RAIN_CONTEXT_MM) | df.timestamp.isin(pos_ts) | df.timestamp.isin(ctrl_ts)].copy()
        keep = keep[~keep.timestamp.isin(excluded)].copy()
        if keep.empty:
            continue

        keep.insert(0, "spot_id", spot_id)

        # Label assignment
        is_pos = keep.timestamp.isin(pos_ts)
        is_ctrl = keep.timestamp.isin(ctrl_ts)

        if strict_negatives:
            # Documented flood = 1, Verified control = 0, Unassessed rainy context = -1
            flood_labels = []
            rules = []
            for t in keep.timestamp:
                if t in pos_ts:
                    flood_labels.append(1)
                    rules.append("documented_incident_window")
                elif t in ctrl_ts:
                    flood_labels.append(0)
                    rules.append("verified_control_non_flood")
                else:
                    flood_labels.append(-1)
                    rules.append("unassessed_rainy_context")
            keep["flood"] = flood_labels
            keep["label_rule"] = rules
        else:
            # Baseline compatibility mode: rainy context hours marked 0
            keep["flood"] = is_pos.astype(int)
            keep["label_rule"] = is_pos.map(lambda p: "documented_incident_window" if p else "rainy_context_sampling")

        keep["incident_id"] = keep.timestamp.map(lambda t: pos.get(t, {}).get("incident_id", ""))
        keep["label_basis"] = keep.timestamp.map(lambda t: pos.get(t, {}).get("basis", "candidate_control"))
        keep["label_confidence"] = keep.timestamp.map(lambda t: pos.get(t, {}).get("confidence", "low" if strict_negatives else "medium"))
        keep["time_precision"] = keep.timestamp.map(lambda t: pos.get(t, {}).get("time_precision", "hour"))
        parts.append(keep)

    cols = [
        "spot_id", "timestamp", "flood", "incident_id", "label_basis", "label_rule",
        "label_confidence", "time_precision",
        "rain_1h_mm", "rain_3h_mm", "rain_6h_mm", "rain_24h_mm", "next_2h_mm"
    ]
    labels = pd.concat(parts, ignore_index=True)[cols] if parts else pd.DataFrame(columns=cols)
    return labels, skipped


# ---------------------------------------------------------------- manifest ---
def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def update_manifest(data_dir: Path, start: str, end: str, incidents: pd.DataFrame) -> None:
    manifest_path = data_dir / "manifests" / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"sources": []}
    now = datetime.now(timezone.utc)
    manifest["generated_at"] = now.isoformat(timespec="seconds")
    manifest["manifest_version"] = "1.2"

    rainfall_files = sorted((data_dir / "raw" / "rainfall").glob("*.json"))
    incident_file = data_dir / "raw" / "incidents.csv"
    dem_files = sorted((data_dir / "raw" / "dem").glob("*.json"))
    osm_files = sorted((data_dir / "raw" / "osm").glob("*.geojson"))

    # Map sources
    sources_by_name = {s.get("name", ""): s for s in manifest.get("sources", [])}

    # 1. Open-Meteo
    om_meta = {
        "name": "Open-Meteo Historical Weather API",
        "type": "hourly_historical_rainfall",
        "variable": "precipitation (mm per hour)",
        "timezone": TZ,
        "access_url": API,
        "date_range": {"start": start, "end": end},
        "fetch_date": now.date().isoformat(),
        "spatial_coverage": "One grid point per study spot (see data/raw/spots.csv)",
        "resolution": "Hourly reanalysis (ERA5-Land / ECMWF blend)",
        "licence_or_attribution": "Attribution to Open-Meteo (CC BY 4.0 for non-commercial / research)",
        "local_path": "data/raw/rainfall/",
        "files": [{"path": str(f.relative_to(data_dir.parent)), "sha256": sha256(f)} for f in rainfall_files],
        "status": "fetched" if rainfall_files else "pending",
        "data_limitations": "Modelled reanalysis precipitation, not physical rain-gauge measurements. Microscale convective storms may be smoothed.",
    }
    sources_by_name["Open-Meteo Historical Weather API"] = om_meta

    # 2. Incidents
    inc_date_start = str(incidents["datetime"].str[:10].min()) if "datetime" in incidents.columns and not incidents.empty else None
    inc_date_end = str(incidents["datetime"].str[:10].max()) if "datetime" in incidents.columns and not incidents.empty else None
    inc_meta = {
        "name": "Flood incident reports (manual)",
        "type": "labels",
        "date_range": {"start": inc_date_start, "end": inc_date_end},
        "fetch_date": now.date().isoformat(),
        "spatial_coverage": "Bengaluru pilot study spots",
        "resolution": "Timestamped incidents (minute/hour precision)",
        "licence_or_attribution": "Each row in data/raw/incidents.csv carries its own source_name and source_url",
        "local_path": "data/raw/incidents.csv",
        "files": [{"path": "data/raw/incidents.csv", "sha256": sha256(incident_file)}] if incident_file.exists() else [],
        "status": "compiled" if not incidents.empty else "pending",
        "data_limitations": "Compiled from verified public news reports and traffic advisories. Unreported localized flood events may not be present in the historical record.",
    }
    sources_by_name["Flood incident reports (manual)"] = inc_meta

    # 3. DEM
    dem_meta = {
        "name": "SRTM elevation data",
        "type": "digital_elevation_model",
        "date_range": None,
        "fetch_date": now.date().isoformat(),
        "spatial_coverage": "Bengaluru study area",
        "resolution": "30m (1 arc-sec) SRTM",
        "licence_or_attribution": "NASA SRTM public domain / USGS / OpenTopography",
        "local_path": "data/raw/dem/",
        "files": [{"path": str(f.relative_to(data_dir.parent)), "sha256": sha256(f)} for f in dem_files],
        "status": "prepared" if dem_files else "pending",
        "data_limitations": "Captures top-of-canopy and building surfaces in dense urban clusters. Ground-level road underpass micro-depressions require engineering surveys.",
    }
    sources_by_name["SRTM elevation data"] = dem_meta

    # 4. OSM
    osm_meta = {
        "name": "OpenStreetMap",
        "type": "road_and_waterway_network",
        "date_range": None,
        "fetch_date": now.date().isoformat(),
        "spatial_coverage": "Bengaluru study area",
        "resolution": "Road and open surface canal segment geometry (GeoJSON)",
        "licence_or_attribution": "© OpenStreetMap contributors, ODbL",
        "local_path": "data/raw/osm/",
        "files": [{"path": str(f.relative_to(data_dir.parent)), "sha256": sha256(f)} for f in osm_files],
        "status": "prepared" if osm_files else "pending",
        "data_limitations": "OSM waterways reflect open surface streams and major canals (Rajakaluves); they DO NOT represent underground closed stormwater pipe networks.",
    }
    sources_by_name["OpenStreetMap"] = osm_meta

    manifest["sources"] = list(sources_by_name.values())
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# -------------------------------------------------------------------- main ---
def load_inputs(data_dir: Path):
    spots = pd.read_csv(data_dir / "raw" / "spots.csv", dtype={"spot_id": str})
    incidents = pd.read_csv(data_dir / "raw" / "incidents.csv", dtype=str)
    # Check minimum required identification columns
    missing = [c for c in ["incident_id", "spot_id"] if c not in incidents.columns]
    if missing:
        sys.exit(f"incidents.csv is missing required columns: {missing}")
    return spots, incidents


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data")
    ap.add_argument("--start", help="YYYY-MM-DD (default: Jan 1 of earliest incident year)")
    ap.add_argument("--end", help="YYYY-MM-DD (default: end of latest incident year, capped to archive lag)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch from API even if cached")
    ap.add_argument("--strict-negatives", action="store_true", help="use 3-state labels: 1=flood, 0=verified control, -1=unknown")
    args = ap.parse_args()
    data_dir: Path = args.data_dir

    spots, incidents = load_inputs(data_dir)
    if incidents.empty:
        sys.exit("data/raw/incidents.csv has no rows. Add verified incidents first (see docs/DATA_SOURCES.md).")

    # Determine date range from incidents
    if "datetime" in incidents.columns:
        dates = pd.to_datetime(incidents["datetime"].str[:10])
    elif "date" in incidents.columns:
        dates = pd.to_datetime(incidents["date"])
    else:
        sys.exit("incidents.csv must contain either 'datetime' or 'date' column.")

    start = date.fromisoformat(args.start) if args.start else date(int(dates.dt.year.min()), 1, 1)
    latest = date(int(dates.dt.year.max()), 12, 31)
    cap = date.today() - timedelta(days=ARCHIVE_LAG_DAYS)
    end = date.fromisoformat(args.end) if args.end else min(latest, cap)

    if start > end:
        sys.exit(f"start date {start} is after end date {end}")
    chunks = year_chunks(start, end)

    raw_dir = data_dir / "raw" / "rainfall"
    out_dir = data_dir / "processed" / "rainfall"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    frames: dict[str, pd.DataFrame] = {}
    feature_parts: list[pd.DataFrame] = []

    print(f"Processing rainfall for {len(spots)} spots across {start} .. {end}...")
    for spot in spots.itertuples():
        print(f"  {spot.spot_id} ({spot.name})")
        raw = load_raw_rainfall(pd.Series(spot._asdict()), chunks, raw_dir, args.refresh)
        proc_df = process_rainfall(raw)
        frames[spot.spot_id] = proc_df
        proc_df.to_csv(out_dir / f"{spot.spot_id}.csv", index=False)

        # Merge with spot properties for combined feature matrix
        sp_feat = proc_df.copy()
        sp_feat.insert(0, "spot_id", spot.spot_id)
        feature_parts.append(sp_feat)

    # Save combined multi-spot features
    combined_features = pd.concat(feature_parts, ignore_index=True)
    combined_features.to_csv(data_dir / "processed" / "features.csv", index=False)
    print(f"Saved {len(combined_features)} feature rows to data/processed/features.csv")

    # Build and save labels
    labels, skipped = build_labels(frames, incidents, strict_negatives=args.strict_negatives)
    labels.to_csv(data_dir / "processed" / "labels.csv", index=False)
    print(f"Saved {len(labels)} label rows to data/processed/labels.csv")

    # Update dataset manifest
    update_manifest(data_dir, start.isoformat(), end.isoformat(), incidents)

    pos = int((labels.flood == 1).sum())
    neg = int((labels.flood == 0).sum())
    unk = int((labels.flood == -1).sum())
    print("\nData Grounding Summary:")
    print(f"  Incidents processed : {len(incidents) - len(skipped)} of {len(incidents)}")
    for iid, why in skipped:
        print(f"    skipped {iid}: {why}")
    print(f"  Documented flood hours (1)   : {pos}")
    print(f"  Verified non-flood hours (0) : {neg}")
    if unk > 0:
        print(f"  Unknown / unassessed hours (-1): {unk} (excluded from precision/recall metrics)")
    print("  Done. Manifest updated with SHA-256 hashes.")


if __name__ == "__main__":
    main()
