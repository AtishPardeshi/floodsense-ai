# FloodSense AI - Data Sources & Provenance Specification

This document defines the schemas, provenance requirements, sourcing procedures, and limitations for all data layers used in FloodSense AI.

---

## 1. Study Spots (`data/raw/spots.csv`)

One row per monitored hotspot or underpass in Bengaluru.
- `spot_id`: Unique identifier (e.g. `silk_board`, `kr_circle`).
- `name`: Human-readable name.
- `lat`, `lng`: WGS84 geographic coordinates. Coordinates must pinpoint the carriageway or lowest underpass section.
- `notes`: Specific spatial context or sampling notes.

---

## 2. Historical Incident Data (`data/raw/incidents.csv`)

Compiled evidence of real, historical urban flood events. **Fabrication of dates, times, spots, or severity is strictly prohibited.**

### Schema:
| Column | Type | Description |
|---|---|---|
| `incident_id` | string | Unique identifier (e.g., `i001`). |
| `event_id` | string | Identifier grouping multi-spot events (e.g., `ev_20220905_deluge`). |
| `spot_id` | string | Must match a valid ID in `spots.csv`. |
| `datetime` | ISO 8601 | Local timestamp (`YYYY-MM-DDTHH:MM:SS+05:30`) or date (`YYYY-MM-DD`). |
| `latitude` | float | Latitude of the reported incident. |
| `longitude` | float | Longitude of the reported incident. |
| `severity` | int (1-3) | 1 = surface water on road, 2 = traffic halted / impassable, 3 = vehicle submergence / property inundation. |
| `source_name` | string | Name of publication, authority, or monitoring agency (e.g., The Hindu, Deccan Herald, Bengaluru Traffic Police). |
| `source_url` | string | Direct URL to news report, tweet/X alert, or government bulletin. |
| `source_type` | string | `news_report`, `traffic_advisory`, `official_bulletin`, `citizen_report`. |
| `label_confidence` | string | `high`, `medium`, `low`. |
| `time_precision` | string | `minute` (exact minute known), `hour` (hour window known), `day` (date known, exact hour unknown). |
| `verification_status` | string | `verified` (cross-referenced and confirmed), `unverified`, `disputed`. |
| `notes` | string | Ambiguities, impact descriptions, or caveats. |

### Verification Protocols:
1. **Direct Source Confirmation**: Only events reported by established news outlets or official traffic/municipal authorities (BTP, BBMP, KSNDMC) are recorded.
2. **Approximate Timestamps**: When a report specifies a time (e.g., "around 3:30 PM"), record `time_precision="minute"`. If only morning/evening or date is specified, record `time_precision="hour"` or `time_precision="day"`.
3. **No Event Invention**: If verified incidents cannot be established for a location, the dataset remains honestly incomplete.

---

## 3. Rainfall Data (`data/raw/rainfall/`, `data/processed/rainfall/`)

### Source:
Open-Meteo Historical Weather API (`https://archive-api.open-meteo.com/v1/archive`).
- **Variable**: Hourly precipitation (`precipitation` in mm).
- **Timezone**: `Asia/Kolkata` (Indian Standard Time, UTC+05:30).
- **Spatial Coverage**: Coordinate-sampled point reanalysis per study spot.
- **Licence & Attribution**: Open-Meteo terms (CC BY 4.0 for non-commercial/academic with attribution).

### Engineering Features:
- `rain_1h_mm`: Cumulative precipitation falling in the preceding 1 hour.
- `rain_3h_mm`: Cumulative precipitation falling in the preceding 3 hours (rolling sum).
- `rain_6h_mm`: Cumulative precipitation falling in the preceding 6 hours (rolling sum).
- `rain_24h_mm`: Cumulative precipitation falling in the preceding 24 hours (rolling sum).
- `next_2h_mm`: Cumulative precipitation in the subsequent 2 hours (forecast proxy).

### Honest Scientific Limitations:
1. **Reanalysis vs. Gauge**: Values are modelled reanalysis grid outputs (ERA5-Land / ECMWF), not physical tipping-bucket rain-gauge measurements. Local convective micro-bursts may be smoothed or underestimated.
2. **Future-Information Leakage Warning**: `next_2h_mm` uses observed future rainfall as a proxy for a perfect 2-hour nowcast. It must **never** be used as a causal feature in real-time inference models; it serves solely for retrospective upper-bound evaluation.

---

## 4. 3-State Ground-Truth Labeling (`data/processed/labels.csv`)

Labels are classified into three explicit states:
- **`1` = Documented Flood**: Confirmed incident at this spot-hour. Assigned to hours within +/- 1 hour of the reported incident timestamp (or the peak-rain hour of the day if only the date was known).
- **`0` = Credible Non-Flood**: Verified control observations during rainfall where conditions were monitored and confirmed clear. The absence of a news report alone does **not** constitute proof of non-flooding.
- **`-1` = Unknown / Insufficient Evidence**: Heavy-rain hours with no explicit reporting or assessment. These are retained for transparent auditing but **must be excluded from precision/recall metric computations**.

### Ambiguity Window:
Hours within +/- 3 hours directly adjacent to a flood window are excluded from negative/control candidates to avoid mislabeling rising or receding water levels.

---

## 5. Digital Elevation Model (DEM) (`data/raw/dem/`)

- **Primary Source**: SRTM (Shuttle Radar Topography Mission) 30m / 90m global elevation dataset or OpenTopography / Copernicus DEM.
- **Attribution**: NASA / USGS / OpenTopography.
- **Usage**: Used to compute relative depression depth (`rel_depth_m`) and local terrain slope.
- **Handling**: If elevation data for a coordinate or tile is unavailable, services return safe `unavailable` statuses and do not fabricate elevation numbers.

---

## 6. OpenStreetMap Vector Data (`data/raw/osm/`)

- **Source**: OpenStreetMap (OSM) via Overpass API.
- **Attribution**: `© OpenStreetMap contributors, ODbL`.
- **Formats**: GeoJSON extracts for highway segments (`highway=*`) and waterway lines (`waterway=*`).
- **Limitation Warning**: OSM `waterway=*` tags (canals, streams, drains) represent visible open surface channels and natural valleys (Rajakaluves). They **do not** document underground municipal stormwater pipes or closed drainage networks. Do not assume all OSM waterways represent functional drains.
