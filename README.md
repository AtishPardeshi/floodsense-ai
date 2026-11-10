# FloodSense AI

Hyperlocal flood early-warning platform for Bengaluru (IBM Bobathon: Build for Bengaluru).

FloodSense AI forecasts which streets, underpasses, and low-lying transit corridors in Bengaluru will flood within the next 2 hours based on real-time and forecast precipitation combined with physical topographical and infrastructural susceptibility.

---

## Quick Start

### 1. Start Both Backend and Frontend
```bash
./start.sh
```
- **Backend API**: http://localhost:8000/api/risk?rain_1h_mm=40&rain_3h_mm=80&forecast_2h_mm=60
- **Interactive Map Application**: http://localhost:5173

---

## Phase 1: Real-World Data Grounding Workflow

The data foundation pipeline is designed to be completely reproducible, self-contained, and runnable offline with cached data.

### 1. Environment Setup & Dependencies
```bash
# Python backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..

# Frontend
cd frontend
npm install
cd ..
```

### 2. Prepare Digital Elevation Model (DEM)
Prepares elevation data for the Bengaluru bounding box. Supports verified offline benchmark samples, Open-Elevation API, and OpenTopography SRTM 30m:
```bash
# Offline benchmark sample (default):
python backend/scripts/download_dem.py --provider sample

# Or query Open-Elevation API for study coordinates:
python backend/scripts/download_dem.py --provider open-elevation

# Or download 30m SRTM GeoTIFF via OpenTopography:
python backend/scripts/download_dem.py --provider opentopography --api-key YOUR_API_KEY
```

### 3. Prepare OpenStreetMap (OSM) Vectors
Extracts road and open drainage/canal networks (Rajakaluves) as GeoJSON with ODbL attribution:
```bash
python backend/scripts/prepare_osm.py
```

### 4. Fetch & Process Historical Rainfall & Ground-Truth Labels
Queries the Open-Meteo Historical Weather API for the 8 pilot spots across documented storm periods (2022–2024), caches raw responses in `data/raw/rainfall/`, computes rolling features (`rain_1h_mm`, `rain_3h_mm`, `rain_6h_mm`, `rain_24h_mm`, and forecast proxy `next_2h_mm`), generates 3-state labels (`1` = flood, `0` = verified control, `-1` = unmonitored unknown), and updates the dataset manifest:
```bash
# Standard run (uses local cache if available):
python backend/scripts/prepare_data.py

# With strict 3-state grounding (labels: 1 = flood, 0 = verified control, -1 = unknown):
python backend/scripts/prepare_data.py --strict-negatives

# Optional: custom date range
python backend/scripts/prepare_data.py --start 2022-09-01 --end 2024-10-31
```

Generated outputs:
- `data/processed/rainfall/<spot_id>.csv`: Rolling accumulation features per spot.
- `data/processed/features.csv`: Multi-spot unified feature matrix.
- `data/processed/labels.csv`: Ground-truth spot-hour labels with provenance metadata.
- `data/processed/validation_results.json`: Retrospective event-based model evaluation metrics.
- `data/manifests/dataset_manifest.json`: Cryptographic SHA-256 provenance tracking.

---

## Phase 2: Historical Validation & Storm Replay

### 1. Run Historical Model Evaluation
Runs retrospective event-based evaluation against documented historical incidents, calculates event/incident recall, computes warning lead times, and generates honest scientific disclaimers:
```bash
python backend/scripts/evaluate.py
```
Generated reports:
- [`docs/VALIDATION_REPORT.md`](docs/VALIDATION_REPORT.md): Detailed markdown evaluation report.
- [`data/processed/validation_results.json`](data/processed/validation_results.json): Structured JSON metrics.

### 2. Historical Storm Replay API & Simulation UI
The frontend includes a toggle between **Live Rain Simulation** and **Historical Storm Replay**:
- Documented storms: *September 5, 2022 Deluge*, *May 21, 2023 KR Circle Cloudburst*, and *October 21, 2024 Flash Flooding*.
- REST Endpoints:
  - `GET /api/replay/events`: List available documented storms.
  - `POST /api/replay/start/{event_id}`: Start a chronological replay session.
  - `GET /api/replay/{run_id}/state`: Current timestep state and predictions.
  - `POST /api/replay/{run_id}/next`: Step forward 1 hour.
  - `POST /api/replay/{run_id}/pause`: Pause simulation.
  - `POST /api/replay/{run_id}/resume`: Resume simulation.
  - `POST /api/replay/{run_id}/reset`: Reset to initial timestep.
  - `GET /api/replay/{run_id}/history`: Chronological timeline history.

---

## Data Structure
```
data/
├── raw/
│   ├── spots.csv                     # 8 pilot locations (coordinates & IDs)
│   ├── incidents.csv                 # 14 verified, sourced historical events
│   ├── rainfall/                     # Cached Open-Meteo raw JSON responses
│   ├── dem/                          # SRTM elevation benchmark grid & metadata
│   └── osm/                          # Road & waterway GeoJSON networks
├── processed/
│   ├── rainfall/                     # Per-spot processed rolling rainfall CSVs
│   ├── features.csv                  # Unified multi-spot feature matrix
│   ├── labels.csv                    # Ground-truth labels (1, 0, -1)
│   └── validation_results.json       # Historical evaluation metrics
├── replay/                           # Historical storm scenarios for replay
└── manifests/
    └── dataset_manifest.json         # Provenance, licenses, and SHA-256 hashes
```

---

## Automated Tests

Run the full backend test suite covering the physical risk engine, REST APIs, data ingestion pipeline, terrain services, dataset manifest integrity, validation logic, and storm replay lifecycle:
```bash
PYTHONPATH=backend pytest backend/tests -v
```

---

## Phase 3: Citizen Intelligence, Human Verification & Response Coordination

### 1. Citizen Web Application & Installable PWA
- **Mobile-First Reporting**: Accessible citizen reporting workflow (`📝 Report`) supporting GPS geo-location, map pin drops, camera/photo uploads, depth measurements, and control reports (roads confirmed clear).
- **Local-First & Offline Resilience**: Service worker caching (`sw.js`), Web App Manifest (`manifest.webmanifest`), and IndexedDB/LocalStorage queue (`ConnectionStatusBanner.tsx`) ensuring citizens can log reports offline with automatic background sync when connectivity resumes.
- **Transparent Report Tracking**: Real-time status lookup (`🔍 Track`) with unique alphanumeric tracking tokens (`rep_...`), showing review states (`submitted` $\rightarrow$ `under_review` $\rightarrow$ `approved` / `rejected` / `needs_info`).

### 2. BBMP Human Verification & Operational Evidence Overlay
- **Triage Queue**: Protected municipal operator console (`🛡️ BBMP`, header `X-Operator-Key`) with automated duplicate detection alerts, proximity clustering, and full audit trails recording reviewer identity, decision, timestamp, and justification.
- **Operational Evidence Overlay (`📊 Evidence`)**: Decoupled evidence aggregator that consumes only approved reports, tracks evidence freshness (fresh $\le 2\text{h}$, recent $\le 6\text{h}$, decayed $6\text{--}24\text{h}$), and displays signals on monitored corridors without double-counting duplicate reports.
- **Physical Baseline Isolation**: Evidence signals are kept strictly decoupled from the frozen physical risk model and historical storm replay scenarios.

### 3. Civic Response Coordination & Local In-App Notifications
- **Deterministic Prioritisation**: Automatically derives response task priorities (`P1_CRITICAL`, `P2_HIGH`, `P3_MEDIUM`, `P4_LOW`) based on verified severity, nearby corroborating reports, evidence freshness, and physical terrain depression depth (`rel_depth_m`).
- **Field Responder Console (`🚜 Field`)**: Dedicated workspace for emergency response teams (`BBMP_Rapid_Unit_1`, `BBMP_Unit_7`, etc.), supporting task progression (`assigned` $\rightarrow$ `in_progress` $\rightarrow$ `resolved`), timeline progress notes, and photographic completion evidence.
- **Local-First In-App Notification Centre (`🔔 Alerts`)**: Real-time operational event stream categorized by audience (Operator, Field Units, Public Advisories). Public emergency alerts feature a strict human operator authorization gate before delivery.

---

## Project Status: Vertical Slice 1 + Phase 1 Data Grounding + Phase 2 Replay & Validation + Phase 3 Citizen Intelligence & Civic Coordination

- [x] **Refactored Physical Risk Engine**: Modular `PhysicalRiskModel` (`physical_risk.py`) with configurable weights, slope integration, and safe missing-data re-normalization.
- [x] **Integration Layer**: `risk_engine.py` orchestrating physical baseline and optional `MLRiskModel` (`ml_risk_model.py`) while preserving 100% backward compatibility.
- [x] **Event-Based Historical Validation**: `validation.py` & `evaluate.py` tracking recall, warning lead time, and honestly reporting precision/false-alarm as unavailable due to zero negative controls.
- [x] **Deterministic Storm Replay Engine**: `replay_engine.py` & `scenarios.py` playing back historical storms step-by-step with complete isolation between model predictions and actual flood outcomes.
- [x] **Replay REST API**: Full lifecycle endpoints for scenario listing, stepping, pausing, and history.
- [x] **Live Weather Service**: `weather_service.py` with 15-minute local disk cache, live sync button in UI, and offline failover.
- [x] **Bilingual AI Early-Warning Agent**: `agent_service.py` generating municipal pump/barricade directives and citizen travel alerts in English and Kannada.
- [x] **Citizen PWA & Offline Reporting**: Installable web app with GPS capture, photo evidence upload, offline draft queuing, and tracking tokens.
- [x] **Operator Verification Dashboard**: Secure triage console with duplicate warnings, spatial proximity clustering, and decision audit logs.
- [x] **Operational Evidence Overlay**: Independent evidence aggregator computing evidence levels, confidence, and freshness decay windows.
- [x] **Civic Response Coordination**: Transparent deterministic task prioritization, field responder workspace, and local in-app notification centre with human approval gates.
- [x] **Comprehensive Test Suite**: 86 automated pytest tests across 16 test suites passing in ~1.4s. Zero frontend TypeScript errors (`tsc && vite build`).

---

## Honest Engineering Disclaimers

1. **Topographic Baseline Estimates**:
   - Spot depression depth (`rel_depth_m`), upstream catchment (`catchment_ha`), and drainage proximity (`drain_dist_m`) are currently baseline engineering placeholder estimates in `fixtures.py`. They are **NOT** measured GIS outputs or hydrodynamic pipe simulations.
   - Terrain slope (`slope_pct`) is dynamically extracted from SRTM DEM elevation data using central differences.
2. **Subsurface vs Surface Drainage**:
   - OpenStreetMap waterways (`waterways.geojson`) represent open surface canals (Rajakaluves) and natural valleys. They **DO NOT** represent underground closed municipal stormwater pipes or pumping stations.
3. **Reanalysis Grid Smoothing**:
   - Archived rainfall is derived from Open-Meteo ERA5-Land reanalysis (~9–30 km grid cell blend). Highly localized convective cloudbursts are attenuated at grid scale. Retrospective reanalysis sensitivity should not be conflated with operational nowcast precision.
4. **Zero False Claims of Precision**:
   - Because open historical records contain zero verified negative controls (dry underpasses during storms), precision and false alarm rates are reported as `Unavailable`, not fabricated.

---

## Roadmap / Future Enhancements

1. **Machine Learning Model Benchmarking** (Train XGBoost/LightGBM classifier on `labels.csv` alongside baseline formula).
2. **LiDAR & Municipal Storm Pipe GIS Ingestion** (Replace placeholder catchment and depth values with measured hydrodynamic network surveys).
3. **Live Crowdsourced Ground-Truth Ingestion** (Citizen verification channel for true negative controls during monsoon storms).
