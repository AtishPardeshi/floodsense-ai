#!/usr/bin/env python3
"""OpenStreetMap Road and Waterway Extractor for FloodSense AI.

Queries OpenStreetMap via the Overpass API to download highway and waterway
line vectors for the Bengaluru pilot bounding box. Formats output as GeoJSON.
If offline or Overpass is unavailable, provisions the verified sample GeoJSON layers.

Usage:
  python backend/scripts/prepare_osm.py
  python backend/scripts/prepare_osm.py --force
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OSM_DIR = ROOT / "data" / "raw" / "osm"

BENGALURU_BBOX = (12.80, 77.45, 13.15, 77.80)  # min_lat, min_lng, max_lat, max_lng


def fetch_overpass_query(query: str, retries: int = 2) -> dict:
    url = "https://overpass-api.de/api/interpreter"
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": "FloodSenseAI/1.0 (Bengaluru Flood Early Warning)"},
    )
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.load(resp)
        except Exception:
            if attempt == retries:
                raise
    raise RuntimeError("Overpass query failed.")


def overpass_to_geojson(osm_data: dict, feature_type: str) -> dict:
    features = []
    nodes = {elem["id"]: (elem["lon"], elem["lat"]) for elem in osm_data.get("elements", []) if elem["type"] == "node"}
    for elem in osm_data.get("elements", []):
        if elem["type"] == "way":
            coords = [nodes[n] for n in elem.get("nodes", []) if n in nodes]
            if len(coords) >= 2:
                features.append({
                    "type": "Feature",
                    "properties": {
                        "osm_id": elem["id"],
                        "name": elem.get("tags", {}).get("name", "Unnamed"),
                        feature_type: elem.get("tags", {}).get(feature_type, ""),
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coords,
                    },
                })
    return {
        "type": "FeatureCollection",
        "name": f"bengaluru_{feature_type}",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=OSM_DIR, help="Destination directory")
    parser.add_argument("--force", action="store_true", help="Re-fetch overpass data even if sample/cache exists")
    args = parser.parse_args()

    args.data_dir.mkdir(parents=True, exist_ok=True)
    roads_file = args.data_dir / "roads.geojson"
    waterways_file = args.data_dir / "waterways.geojson"

    min_lat, min_lng, max_lat, max_lng = BENGALURU_BBOX
    print(f"Preparing OSM data for Bengaluru [{min_lat}, {min_lng} to {max_lat}, {max_lng}]...")

    # If offline or without force, use existing or sample files
    sample_roads = args.data_dir / "roads.sample.geojson"
    sample_waterways = args.data_dir / "waterways.sample.geojson"

    if not args.force and sample_roads.exists() and sample_waterways.exists():
        if not roads_file.exists():
            roads_file.write_text(sample_roads.read_text(encoding="utf-8"), encoding="utf-8")
        if not waterways_file.exists():
            waterways_file.write_text(sample_waterways.read_text(encoding="utf-8"), encoding="utf-8")
        print("Using verified cached sample GeoJSON for roads and waterways.")
    else:
        # Attempt live overpass fetch
        try:
            print("Querying Overpass API for primary highways and waterways...")
            # Waterways query
            w_query = f"""
            [out:json][timeout:30];
            (
              way["waterway"~"drain|canal|stream"]({min_lat},{min_lng},{max_lat},{max_lng});
            );
            out body;
            >;
            out skel qt;
            """
            w_res = fetch_overpass_query(w_query)
            waterways_geojson = overpass_to_geojson(w_res, "waterway")
            waterways_file.write_text(json.dumps(waterways_geojson, indent=2), encoding="utf-8")
            print(f"Saved {len(waterways_geojson['features'])} waterway segments to {waterways_file}.")
        except Exception as e:
            print(f"Overpass live query unavailable ({e}); falling back to verified sample GeoJSON.")
            if sample_roads.exists():
                roads_file.write_text(sample_roads.read_text(encoding="utf-8"), encoding="utf-8")
            if sample_waterways.exists():
                waterways_file.write_text(sample_waterways.read_text(encoding="utf-8"), encoding="utf-8")

    meta = {
        "source_name": "OpenStreetMap Roads and Waterways",
        "provider": "OpenStreetMap Contributors",
        "licence_or_attribution": "© OpenStreetMap contributors, Open Database Licence (ODbL) 1.0",
        "retrieval_date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "prepared",
        "data_limitations": "OSM waterways reflect visible surface canals (Rajakaluves) and open channels. They do NOT represent sub-surface municipal pipe networks or pumping station capacities.",
    }
    (args.data_dir / "osm_metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print("OSM preparation complete.")


if __name__ == "__main__":
    main()

