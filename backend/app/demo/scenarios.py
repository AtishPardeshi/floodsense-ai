"""Documented historical storm scenarios for FloodSense AI.

Derived from verified flood events in data/raw/incidents.csv and cached Open-Meteo
hourly reanalysis precipitation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ScenarioDefinition:
    event_id: str
    name: str
    date_str: str
    start_time: str
    end_time: str
    description: str
    impacted_spots: list[str]
    max_severity: int
    citations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


HISTORICAL_SCENARIOS: dict[str, ScenarioDefinition] = {
    "ev_20220905_deluge": ScenarioDefinition(
        event_id="ev_20220905_deluge",
        name="September 5, 2022 Deluge (Historic Urban Flood)",
        date_str="2022-09-04 to 2022-09-05",
        start_time="2022-09-04 12:00:00",
        end_time="2022-09-05 18:00:00",
        description="Overnight extreme cloudburst causing widespread lake breaches, Outer Ring Road submergence (EcoSpace), and city-wide traffic paralysis. Tractors and rescue rafts deployed.",
        impacted_spots=["bellandur", "silk_board", "mahadevapura", "hsr_layout", "agara"],
        max_severity=3,
        citations=[
            "The Hindu: Tractors deployed on Outer Ring Road (article65851896)",
            "Deccan Herald: Silk Board waist-deep water (1142277)",
            "Times of India: ORR tech parks inundated (93998980)",
        ],
    ),
    "ev_20230521_cloudburst": ScenarioDefinition(
        event_id="ev_20230521_cloudburst",
        name="May 21, 2023 KR Circle Cloudburst",
        date_str="2023-05-21",
        start_time="2023-05-21 08:00:00",
        end_time="2023-05-21 22:00:00",
        description="High-intensity pre-monsoon convective cloudburst causing neck-deep flooding in KR Circle underpass and fatal vehicle submergence.",
        impacted_spots=["kr_circle"],
        max_severity=3,
        citations=[
            "The Hindu: Woman dies as car submerged at KR Circle underpass (article66877283)",
            "Deccan Herald: Pre-monsoon storm inundates central Bengaluru underpasses",
        ],
    ),
    "ev_20241021_cloudburst": ScenarioDefinition(
        event_id="ev_20241021_cloudburst",
        name="October 21, 2024 Late-Monsoon Flash Flooding",
        date_str="2024-10-21 to 2024-10-22",
        start_time="2024-10-21 12:00:00",
        end_time="2024-10-22 04:00:00",
        description="Evening cloudburst inundating Agara underpass, Mahadevapura arterial junctions, and residential roads in Indiranagar.",
        impacted_spots=["agara", "mahadevapura", "indiranagar"],
        max_severity=2,
        citations=[
            "Deccan Herald: Agara underpass submerged and closed (3242118)",
            "The Hindu: Arterial roads inundated in Mahadevapura (article68781920)",
        ],
    ),
}

