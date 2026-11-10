"""Seed spots for the pilot zone.

IMPORTANT DATA LIMITATION NOTICE:
- Coordinates pinpoint monitored carriageways and underpass sections in Bengaluru.
- 'rel_depth_m' (depression depth), 'catchment_ha' (upstream catchment), and 'drain_dist_m'
  (drainage proximity) are BASELINE ENGINEERING PLACEHOLDER ESTIMATES. They are NOT
  measured GIS outputs or full hydraulic pipe network simulations.
- OpenStreetMap waterways represent open surface canals (Rajakaluves) and DO NOT
  represent underground closed municipal pipe networks.
- 'past_incidents' are derived dynamically from verified historical records in
  'data/raw/incidents.csv' to ensure complete alignment with real-world evidence.
"""
from __future__ import annotations

import csv
from pathlib import Path

from app.database.schemas import Spot

_INCIDENTS_PATH = Path(__file__).resolve().parents[3] / "data" / "raw" / "incidents.csv"


def _load_verified_incident_counts() -> dict[str, int]:
    """Dynamically counts verified incidents per spot from data/raw/incidents.csv."""
    counts: dict[str, int] = {}
    if _INCIDENTS_PATH.exists():
        try:
            with open(_INCIDENTS_PATH, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sp = row.get("spot_id", "").strip()
                    if sp:
                        counts[sp] = counts.get(sp, 0) + 1
        except Exception:
            pass
    return counts


_VERIFIED_COUNTS = _load_verified_incident_counts()

SPOTS: list[Spot] = [
    Spot(id="silk_board", name="Silk Board Junction", lat=12.9177, lng=77.6233,
         rel_depth_m=4.5, catchment_ha=260, drain_dist_m=320,
         past_incidents=_VERIFIED_COUNTS.get("silk_board", 2)),
    Spot(id="bellandur", name="Bellandur Lake Edge", lat=12.9352, lng=77.6745,
         rel_depth_m=5.5, catchment_ha=290, drain_dist_m=150,
         past_incidents=_VERIFIED_COUNTS.get("bellandur", 2)),
    Spot(id="hsr_layout", name="HSR Layout Sector 2", lat=12.9116, lng=77.6389,
         rel_depth_m=3.0, catchment_ha=140, drain_dist_m=220,
         past_incidents=_VERIFIED_COUNTS.get("hsr_layout", 1)),
    Spot(id="agara", name="Agara Underpass", lat=12.9250, lng=77.6480,
         rel_depth_m=4.0, catchment_ha=180, drain_dist_m=260,
         past_incidents=_VERIFIED_COUNTS.get("agara", 2)),
    Spot(id="kr_circle", name="KR Circle Underpass", lat=12.9763, lng=77.5929,
         rel_depth_m=3.5, catchment_ha=110, drain_dist_m=120,
         past_incidents=_VERIFIED_COUNTS.get("kr_circle", 2)),
    Spot(id="hebbal", name="Hebbal Flyover Approach", lat=13.0358, lng=77.5970,
         rel_depth_m=2.5, catchment_ha=200, drain_dist_m=180,
         past_incidents=_VERIFIED_COUNTS.get("hebbal", 2)),
    Spot(id="mahadevapura", name="Mahadevapura Main Road", lat=12.9910, lng=77.6980,
         rel_depth_m=2.0, catchment_ha=90, drain_dist_m=300,
         past_incidents=_VERIFIED_COUNTS.get("mahadevapura", 2)),
    Spot(id="indiranagar", name="Indiranagar 100ft Road", lat=12.9719, lng=77.6412,
         rel_depth_m=0.8, catchment_ha=40, drain_dist_m=60,
         past_incidents=_VERIFIED_COUNTS.get("indiranagar", 1)),
]
