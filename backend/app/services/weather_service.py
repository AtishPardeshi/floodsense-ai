"""Live weather ingestion service for FloodSense AI.

Queries Open-Meteo Forecast API for real-time precipitation and nowcasts
across Bengaluru pilot coordinates.
Provides local in-memory caching (15-minute TTL) and safe offline fallback.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database.schemas import Rainfall, Spot
from app.demo.fixtures import SPOTS

ROOT = Path(__file__).resolve().parents[3]
FORECAST_API = "https://api.open-meteo.com/v1/forecast"
WEATHER_CACHE_DIR = ROOT / "data" / "raw" / "weather"
CACHE_TTL_SEC = 900  # 15 minutes


@dataclass
class SpotWeather:
    spot_id: str
    name: str
    lat: float
    lng: float
    current_rain_mm_h: float
    past_3h_mm: float
    past_6h_mm: float
    forecast_2h_mm: float
    timestamp: str
    source: str = "open-meteo-forecast"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LiveWeatherSummary:
    timestamp: str
    bengaluru_avg_rain_1h: float
    bengaluru_max_rain_1h: float
    bengaluru_avg_forecast_2h: float
    spots_weather: list[SpotWeather]
    is_live: bool
    data_source: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "bengaluru_avg_rain_1h": self.bengaluru_avg_rain_1h,
            "bengaluru_max_rain_1h": self.bengaluru_max_rain_1h,
            "bengaluru_avg_forecast_2h": self.bengaluru_avg_forecast_2h,
            "spots_weather": [s.to_dict() for s in self.spots_weather],
            "is_live": self.is_live,
            "data_source": self.data_source,
            "note": self.note,
        }


class WeatherService:
    """Manages live weather querying and caching for Bengaluru spots."""

    def __init__(self, cache_dir: Path | None = None, api_timeout_sec: float = 2.0):
        self.cache_dir = cache_dir or WEATHER_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_timeout_sec = api_timeout_sec
        self._cached_summary: LiveWeatherSummary | None = None
        self._last_fetch_time: float = 0.0
        self._load_disk_cache()

    def _load_disk_cache(self) -> None:
        """Loads persistent cache from disk if available."""
        cache_file = self.cache_dir / "latest_weather.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                spots = [SpotWeather(**s) for s in data.get("spots_weather", [])]
                self._cached_summary = LiveWeatherSummary(
                    timestamp=data.get("timestamp", ""),
                    bengaluru_avg_rain_1h=data.get("bengaluru_avg_rain_1h", 0.0),
                    bengaluru_max_rain_1h=data.get("bengaluru_max_rain_1h", 0.0),
                    bengaluru_avg_forecast_2h=data.get("bengaluru_avg_forecast_2h", 0.0),
                    spots_weather=spots,
                    is_live=data.get("is_live", False),
                    data_source=data.get("data_source", "Cached Local State"),
                    note=data.get("note", "Loaded from persistent local cache."),
                )
                self._last_fetch_time = time.time()
            except Exception:
                pass

    def _fetch_from_api(self, spot: Spot) -> dict[str, Any]:
        """Queries Open-Meteo forecast API for a single location."""
        params = urllib.parse.urlencode({
            "latitude": spot.lat,
            "longitude": spot.lng,
            "current": "precipitation",
            "hourly": "precipitation",
            "timezone": "Asia/Kolkata",
            "forecast_hours": 6,
            "past_hours": 6,
        })
        url = f"{FORECAST_API}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "FloodSenseAI/1.0 (Bengaluru)"})
        with urllib.request.urlopen(req, timeout=self.api_timeout_sec) as resp:
            return json.load(resp)

    def get_live_weather(self, force_refresh: bool = False) -> LiveWeatherSummary:
        """Retrieves live weather across all pilot spots with caching and safe fallback."""
        now = time.time()
        if (
            not force_refresh
            and self._cached_summary is not None
            and (now - self._last_fetch_time) < CACHE_TTL_SEC
        ):
            return self._cached_summary

        spot_weathers: list[SpotWeather] = []
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

        try:
            # Query first spot to check connectivity
            first_spot = SPOTS[0]
            first_data = self._fetch_from_api(first_spot)

            # If first spot succeeds, process all
            for spot in SPOTS:
                data = first_data if spot.id == first_spot.id else self._fetch_from_api(spot)
                current_rain = float(data.get("current", {}).get("precipitation", 0.0))

                hourly = data.get("hourly", {})
                precips = hourly.get("precipitation", [])
                if len(precips) >= 8:
                    past_3 = float(sum(precips[3:6]))
                    past_6 = float(sum(precips[0:6]))
                    forecast_2 = float(sum(precips[6:8]))
                else:
                    past_3 = current_rain * 2.0
                    past_6 = current_rain * 3.0
                    forecast_2 = current_rain * 1.5

                sw = SpotWeather(
                    spot_id=spot.id,
                    name=spot.name,
                    lat=spot.lat,
                    lng=spot.lng,
                    current_rain_mm_h=round(current_rain, 1),
                    past_3h_mm=round(past_3, 1),
                    past_6h_mm=round(past_6, 1),
                    forecast_2h_mm=round(forecast_2, 1),
                    timestamp=now_iso,
                    source="open-meteo-forecast-live",
                )
                spot_weathers.append(sw)

            is_live = True
            source_label = "Open-Meteo Forecast Live API"
            note_label = "Real-time precipitation and 2-hour nowcast fetched successfully."

        except Exception as e:
            # Fast failover: if disk cache exists, use it
            if self._cached_summary is not None:
                return self._cached_summary

            # Otherwise use clean baseline fallback
            is_live = False
            source_label = "Local Baseline Fallback (Offline)"
            note_label = f"Live weather API unreachable ({e}). Using offline baseline."
            for spot in SPOTS:
                sw = SpotWeather(
                    spot_id=spot.id,
                    name=spot.name,
                    lat=spot.lat,
                    lng=spot.lng,
                    current_rain_mm_h=0.0,
                    past_3h_mm=0.0,
                    past_6h_mm=0.0,
                    forecast_2h_mm=0.0,
                    timestamp=now_iso,
                    source="offline-fallback",
                )
                spot_weathers.append(sw)

        r1_list = [s.current_rain_mm_h for s in spot_weathers]
        f2_list = [s.forecast_2h_mm for s in spot_weathers]

        summary = LiveWeatherSummary(
            timestamp=now_iso,
            bengaluru_avg_rain_1h=round(sum(r1_list) / len(r1_list), 2) if r1_list else 0.0,
            bengaluru_max_rain_1h=round(max(r1_list), 1) if r1_list else 0.0,
            bengaluru_avg_forecast_2h=round(sum(f2_list) / len(f2_list), 2) if f2_list else 0.0,
            spots_weather=spot_weathers,
            is_live=is_live,
            data_source=source_label,
            note=note_label,
        )

        self._cached_summary = summary
        self._last_fetch_time = now

        try:
            cache_file = self.cache_dir / "latest_weather.json"
            cache_file.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
        except Exception:
            pass

        return summary

    def get_live_risk(self) -> list[dict[str, Any]]:
        """Evaluates physical risk across all spots using current live weather conditions."""
        summary = self.get_live_weather()
        weather_by_id = {sw.spot_id: sw for sw in summary.spots_weather}

        evaluated_spots = []
        for s in SPOTS:
            sw = weather_by_id.get(s.id)
            if sw:
                r = Rainfall(
                    rain_1h_mm=sw.current_rain_mm_h,
                    rain_3h_mm=sw.past_3h_mm,
                    forecast_2h_mm=sw.forecast_2h_mm,
                )
            else:
                r = Rainfall()

            from app.services.risk_engine import score_spot
            spot_risk = score_spot(s, r)
            evaluated_spots.append(spot_risk)

        return sorted([sr.model_dump() for sr in evaluated_spots], key=lambda x: x["risk"], reverse=True)


# Global singleton
weather_service = WeatherService()
