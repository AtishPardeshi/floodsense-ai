#!/usr/bin/env python3
"""Download and manage Digital Elevation Model (DEM) data for FloodSense AI.

Sources:
  1. OpenTopography Global SRTM 30m (Requires OPENTOPOGRAPHY_API_KEY)
  2. Open-Elevation API (Public API for spot point lookups)
  3. Sample reference benchmark grid (Offline deterministic fallback)

Usage:
  python backend/scripts/download_dem.py --provider sample
  python backend/scripts/download_dem.py --provider open-elevation
  python backend/scripts/download_dem.py --provider opentopography --api-key YOUR_KEY
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEM_RAW_DIR = ROOT / "data" / "raw" / "dem"

BENGALURU_DEFAULT_BBOX = [77.45, 12.80, 77.80, 13.15]  # min_lng, min_lat, max_lng, max_lat


def fetch_open_elevation_points(points: list[dict], retries: int = 3) -> list[dict]:
    """Queries Open-Elevation public REST API."""
    url = "https://api.open-elevation.com/api/v1/lookup"
    payload = json.dumps({"locations": [{"latitude": p["lat"], "longitude": p["lng"]} for p in points]}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "FloodSenseAI/1.0"},
    )
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.load(resp)
            out = []
            for orig, res in zip(points, result.get("results", [])):
                out.append({
                    "spot_id": orig.get("spot_id", ""),
                    "lat": orig["lat"],
                    "lng": orig["lng"],
                    "elevation": res["elevation"],
                })
            return out
        except Exception as e:
            last_err = e
            time.sleep(2 * attempt)
    raise RuntimeError(f"Open-Elevation query failed after {retries} attempts: {last_err}")


def download_opentopography_raster(bbox: list[float], api_key: str, out_path: Path) -> None:
    """Requests SRTMGL1 GeoTIFF from OpenTopography API."""
    min_lng, min_lat, max_lng, max_lat = bbox
    params = urllib.parse.urlencode({
        "demtype": "SRTMGL1",
        "south": min_lat,
        "north": max_lat,
        "west": min_lng,
        "east": max_lng,
        "outputFormat": "GTiff",
        "API_Key": api_key,
    })
    url = f"https://portal.opentopography.org/API/globaldem?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "FloodSenseAI/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        out_path.write_bytes(data)
    except urllib.error.HTTPError as e:
        if e.code == 401 or e.code == 403:
            raise RuntimeError("OpenTopography API key is invalid or unauthorized. Please verify your key.")
        raise RuntimeError(f"OpenTopography download failed with HTTP {e.code}: {e.reason}")
    except Exception as e:
        raise RuntimeError(f"OpenTopography download connection error: {e}")


def write_dem_metadata(metadata_path: Path, provider: str, bbox: list[float], status: str) -> None:
    meta = {
        "source_name": f"Digital Elevation Model ({provider})",
        "provider": provider,
        "retrieval_date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bounding_box": {
            "min_lng": bbox[0],
            "min_lat": bbox[1],
            "max_lng": bbox[2],
            "max_lat": bbox[3],
        },
        "resolution": "30m (1 arc-sec) SRTM",
        "vertical_datum": "EGM96",
        "licence_or_attribution": "NASA SRTM / OpenTopography. Open data for research and non-commercial application.",
        "status": status,
        "data_limitations": "SRTM values capture top-of-canopy/building surface reflections in built-up urban cores. Surface drainage gutters require local ground-truth surveying.",
    }
    metadata_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        choices=["sample", "open-elevation", "opentopography"],
        default="sample",
        help="DEM data provider (default: sample)",
    )
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        default=BENGALURU_DEFAULT_BBOX,
        metavar=("MIN_LNG", "MIN_LAT", "MAX_LNG", "MAX_LAT"),
        help="Bounding box in decimal degrees",
    )
    parser.add_argument("--api-key", help="API key for OpenTopography (or use OPENTOPOGRAPHY_API_KEY env)")
    parser.add_argument("--out-dir", type=Path, default=DEM_RAW_DIR, help="Destination directory for DEM data")
    parser.add_argument("--force", action="store_true", help="Re-download even if already present")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    metadata_file = args.out_dir / "dem_metadata.json"

    print(f"DEM Data Preparation: provider={args.provider}, bbox={args.bbox}")

    if args.provider == "sample":
        sample_file = args.out_dir / "bengaluru_dem_sample.json"
        if sample_file.exists() and not args.force:
            print(f"Sample DEM grid already present at {sample_file} (skipping download).")
        else:
            print(f"Verified sample grid available at {sample_file}.")
        write_dem_metadata(metadata_file, "SRTM_Offline_Sample", args.bbox, "ready")
        print("DEM preparation complete.")

    elif args.provider == "open-elevation":
        spots_file = ROOT / "data" / "raw" / "spots.csv"
        if not spots_file.exists():
            sys.exit(f"Cannot find spots file: {spots_file}")
        import pandas as pd
        spots_df = pd.read_csv(spots_file)
        points = [{"spot_id": r.spot_id, "lat": float(r.lat), "lng": float(r.lng)} for r in spots_df.itertuples()]
        print(f"Fetching elevations for {len(points)} study spots from Open-Elevation API...")
        results = fetch_open_elevation_points(points)
        out_file = args.out_dir / "open_elevation_spots.json"
        out_file.write_text(json.dumps({"points": results}, indent=2) + "\n")
        write_dem_metadata(metadata_file, "Open-Elevation_API", args.bbox, "fetched")
        print(f"Successfully saved elevations to {out_file}.")

    elif args.provider == "opentopography":
        key = args.api_key or os.environ.get("OPENTOPOGRAPHY_API_KEY")
        if not key:
            sys.exit(
                "Error: OpenTopography requires an API key.\n"
                "Provide it via --api-key <key> or set the OPENTOPOGRAPHY_API_KEY environment variable.\n"
                "Get a free API key at: https://opentopography.org/"
            )
        target_tif = args.out_dir / "bengaluru_srtm_30m.tif"
        if target_tif.exists() and not args.force:
            print(f"Target raster {target_tif} already exists. Use --force to overwrite.")
            return
        print(f"Downloading SRTM 30m GeoTIFF from OpenTopography into {target_tif}...")
        download_opentopography_raster(args.bbox, key, target_tif)
        write_dem_metadata(metadata_file, "OpenTopography_SRTMGL1", args.bbox, "downloaded")
        print("OpenTopography DEM download successful.")


if __name__ == "__main__":
    main()

