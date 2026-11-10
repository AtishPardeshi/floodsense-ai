"""Terrain elevation and slope service for FloodSense AI.

Extracts elevation and local slope from digital elevation model (DEM) files.
Provides safe missing-data handling, boundary checking, and transparent status reporting.
Never fabricates elevation values.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ElevationStatus = Literal["available", "missing_tile", "out_of_bounds", "unavailable"]

# Bounding box for greater Bengaluru study area (WGS84)
BENGALURU_BBOX = {
    "min_lat": 12.70,
    "max_lat": 13.30,
    "min_lng": 77.30,
    "max_lng": 77.90,
}


@dataclass
class ElevationResult:
    elevation_m: float | None
    status: ElevationStatus
    slope_pct: float | None = None
    source: str = "SRTM_30m"
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "elevation_m": self.elevation_m,
            "status": self.status,
            "slope_pct": self.slope_pct,
            "source": self.source,
            "message": self.message,
        }


class TerrainService:
    """Service to query elevation and terrain slope from local DEM caches."""

    def __init__(self, dem_dir: Path | str | None = None):
        if dem_dir is None:
            # Default to repo root data/raw/dem
            self.dem_dir = Path(__file__).resolve().parents[3] / "data" / "raw" / "dem"
        else:
            self.dem_dir = Path(dem_dir)
        self._cache: dict[tuple[float, float], float] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """Loads any cached DEM grid or sample json files from the dem directory."""
        if not self.dem_dir.exists():
            return

        for p in self.dem_dir.glob("*.json"):
            if "metadata" in p.name:
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                # Support grid point formats
                if isinstance(data, dict) and "points" in data:
                    for pt in data["points"]:
                        lat = round(float(pt["lat"]), 4)
                        lng = round(float(pt["lng"]), 4)
                        self._cache[(lat, lng)] = float(pt["elevation"])
                elif isinstance(data, list):
                    for pt in data:
                        if "lat" in pt and "lng" in pt and "elevation" in pt:
                            lat = round(float(pt["lat"]), 4)
                            lng = round(float(pt["lng"]), 4)
                            self._cache[(lat, lng)] = float(pt["elevation"])
            except Exception:
                continue

    def is_within_bounds(self, lat: float, lng: float) -> bool:
        """Validates coordinates against the study area bounding box."""
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            return False
        return (
            BENGALURU_BBOX["min_lat"] <= lat <= BENGALURU_BBOX["max_lat"]
            and BENGALURU_BBOX["min_lng"] <= lng <= BENGALURU_BBOX["max_lng"]
        )

    def get_elevation(self, lat: float, lng: float, tolerance: float = 0.005) -> ElevationResult:
        """Retrieves elevation in metres above MSL.

        Returns safe unavailable/out_of_bounds statuses without guessing or fabricating.
        """
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            return ElevationResult(
                elevation_m=None,
                status="out_of_bounds",
                message=f"Coordinates ({lat}, {lng}) are physically invalid.",
            )

        if not self.is_within_bounds(lat, lng):
            return ElevationResult(
                elevation_m=None,
                status="out_of_bounds",
                message=f"Coordinates ({lat}, {lng}) are outside the Bengaluru study area.",
            )

        if not self.dem_dir.exists():
            return ElevationResult(
                elevation_m=None,
                status="unavailable",
                message=f"DEM directory {self.dem_dir} does not exist.",
            )

        # Exact key match
        key = (round(lat, 4), round(lng, 4))
        if key in self._cache:
            elev = self._cache[key]
            slope = self.get_slope(lat, lng)
            return ElevationResult(elevation_m=elev, status="available", slope_pct=slope)

        # Nearest neighbor within spatial tolerance (~500m)
        best_dist = float("inf")
        best_elev: float | None = None
        for (c_lat, c_lng), elev in self._cache.items():
            dist = math.hypot(lat - c_lat, lng - c_lng)
            if dist < best_dist:
                best_dist = dist
                best_elev = elev

        if best_elev is not None and best_dist <= tolerance:
            slope = self.get_slope(lat, lng)
            return ElevationResult(elevation_m=best_elev, status="available", slope_pct=slope)

        return ElevationResult(
            elevation_m=None,
            status="missing_tile",
            message=f"No DEM elevation tile or grid cell cached near ({lat:.4f}, {lng:.4f}).",
        )

    def get_slope(self, lat: float, lng: float, delta: float = 0.001) -> float | None:
        """Estimates terrain slope percentage using central differences if neighboring points exist."""
        # Find elevation at +/- delta
        north = self._lookup_raw(lat + delta, lng)
        south = self._lookup_raw(lat - delta, lng)
        east = self._lookup_raw(lat, lng + delta)
        west = self._lookup_raw(lat, lng - delta)

        if north is None or south is None or east is None or west is None:
            return None

        # Distance per degree in meters near Bengaluru latitude (~12.97 deg N)
        meters_per_deg_lat = 110574.0
        meters_per_deg_lng = 111320.0 * math.cos(math.radians(lat))

        dy = 2 * delta * meters_per_deg_lat
        dx = 2 * delta * meters_per_deg_lng

        dz_dy = (north - south) / dy
        dz_dx = (east - west) / dx

        slope_rad = math.atan(math.hypot(dz_dx, dz_dy))
        slope_pct = round(math.tan(slope_rad) * 100, 2)
        return slope_pct

    def _lookup_raw(self, lat: float, lng: float, tolerance: float = 0.005) -> float | None:
        key = (round(lat, 4), round(lng, 4))
        if key in self._cache:
            return self._cache[key]
        for (c_lat, c_lng), elev in self._cache.items():
            if math.hypot(lat - c_lat, lng - c_lng) <= tolerance:
                return elev
        return None

