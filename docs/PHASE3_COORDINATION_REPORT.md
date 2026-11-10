# FloodSense AI — Phase 3: Civic Response Coordination Report

## 1. Executive Summary

Phase 3 introduces **Civic Response Coordination & Local In-App Notifications** to FloodSense AI, closing the loop between citizen intelligence, municipal operator verification, and frontline field response for Bengaluru's urban flood resilience.

All implementations strictly adhere to:
- **Zero baseline degradation**: Phase 1 and Phase 2 physical risk models, dataset manifests, and historical replay scenarios remain frozen and passing.
- **Deterministic Prioritisation**: Priority bands (`P1_CRITICAL`, `P2_HIGH`, `P3_MEDIUM`, `P4_LOW`) are derived via an explicit, auditable mathematical formula based solely on verified incident depth/severity, nearby corroborating reports, evidence freshness, and physical terrain depression (`rel_depth_m`).
- **No Fabricated Data**: No artificial traffic data, population counts, or responder locations are assumed or simulated.
- **Security & Authorization**: Operator commands are guarded by `X-Operator-Key`. Field units can only update tasks explicitly assigned to them (`X-Responder-Id`).
- **Local-First & Safety Gate**: In-app notifications are stored locally in SQLite (`in_app_notifications`) without spamming external SMS/telephony gateways. Public emergency advisories strictly require human operator authorization before in-app delivery.

---

## 2. Architecture & Data Model

### 2.1 Database Schema (Migration V3)

Applied in `backend/app/database/migrations.py`:

```sql
-- 1. Response Coordination Tasks
CREATE TABLE IF NOT EXISTS response_tasks (
    task_id TEXT PRIMARY KEY,
    incident_report_id TEXT,
    spot_id TEXT NOT NULL,
    location_name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('P1_CRITICAL', 'P2_HIGH', 'P3_MEDIUM', 'P4_LOW')),
    priority_reasons_json TEXT,
    assigned_responder_id TEXT,
    assigned_by TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'assigned', 'in_progress', 'resolved', 'cancelled')),
    due_at TEXT,
    resolution_notes TEXT,
    resolution_image_filename TEXT,
    resolved_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(incident_report_id) REFERENCES citizen_reports(report_id)
);

-- 2. Task Progress Notes & Timeline
CREATE TABLE IF NOT EXISTS task_progress_notes (
    note_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    author_role TEXT NOT NULL DEFAULT 'responder',
    note TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES response_tasks(task_id)
);

-- 3. In-App Notifications
CREATE TABLE IF NOT EXISTS in_app_notifications (
    notification_id TEXT PRIMARY KEY,
    task_id TEXT,
    report_id TEXT,
    target_audience TEXT NOT NULL CHECK (target_audience IN ('operator', 'responder', 'public_advisory')),
    target_responder_id TEXT,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    delivery_status TEXT NOT NULL CHECK (delivery_status IN ('logged_locally', 'delivered_in_app', 'acknowledged', 'pending_approval')),
    requires_human_approval INTEGER NOT NULL DEFAULT 0,
    approved_by TEXT,
    approved_at TEXT,
    created_at TEXT NOT NULL
);
```

---

## 3. Deterministic Transparent Prioritisation

Tasks are prioritized using a four-factor scoring model ($0 \le \text{Score} \le 100$):

$$\text{Score} = S_{\text{severity}} + S_{\text{corroboration}} + S_{\text{freshness}} + S_{\text{exposure}}$$

| Contributing Factor | Scoring Rules | Weight |
|---|---|---|
| **1. Verified Severity** | Critical ($\ge 80\text{ cm}$): 40 pts<br>High ($45\text{--}80\text{ cm}$): 30 pts<br>Medium ($15\text{--}45\text{ cm}$): 20 pts<br>Low ($< 15\text{ cm}$): 10 pts | 40 pts max |
| **2. Nearby Evidence Corroboration** | $\ge 3$ approved reports in $1.5\text{ km}$: 25 pts<br>2 approved reports: 15 pts<br>1 approved report: 10 pts<br>0 approved reports: 0 pts | 25 pts max |
| **3. Evidence Freshness** | Fresh ($\le 2\text{ hours}$): 20 pts<br>Recent ($2\text{--}6\text{ hours}$): 10 pts<br>Decayed ($6\text{--}24\text{ hours}$): 5 pts<br>Expired ($> 24\text{ hours}$): 0 pts | 20 pts max |
| **4. Physical Terrain Criticality** | Deep underpass depression ($\text{rel\_depth} \ge 3.5\text{ m}$): 15 pts<br>Moderate depression ($\text{rel\_depth} \ge 2.0\text{ m}$): 10 pts<br>Surface gradient: 5 pts | 15 pts max |

### Priority Thresholds
- **Score $\ge 70$** $\rightarrow$ `P1_CRITICAL` (Target response: $\le 2\text{ hours}$)
- **Score $50\text{--}69$** $\rightarrow$ `P2_HIGH` (Target response: $\le 2\text{ hours}$)
- **Score $30\text{--}49$** $\rightarrow$ `P3_MEDIUM` (Target response: $\le 4\text{ hours}$)
- **Score $< 30$** $\rightarrow$ `P4_LOW` (Target response: $\le 4\text{ hours}$)

Every task stores the complete breakdown and explanation string for total audit transparency.

---

## 4. API Specification

| Method | Endpoint | Authorization | Description |
|---|---|---|---|
| `POST` | `/api/coordination/tasks` | `X-Operator-Key` | Create a new response task with automated deterministic priority |
| `GET` | `/api/coordination/tasks` | Public | List response tasks with filters (`status`, `responder_id`, `spot_id`) |
| `GET` | `/api/coordination/tasks/priority-preview` | Public | Pre-calculate deterministic priority breakdown for a spot/report |
| `GET` | `/api/coordination/tasks/{id}` | Public | Full task details, notes timeline, and priority score factors |
| `POST` | `/api/coordination/tasks/{id}/assign` | `X-Operator-Key` | Assign responder unit (`open` $\rightarrow$ `assigned`) |
| `PATCH` | `/api/coordination/tasks/{id}/status` | `X-Responder-Id` | Update state (`assigned` $\rightarrow$ `in_progress`), enforced to assigned unit |
| `POST` | `/api/coordination/tasks/{id}/resolve` | `X-Responder-Id` | Resolve task with mandatory completion notes and photo evidence |
| `POST` | `/api/coordination/tasks/{id}/notes` | `X-Responder-Id` | Append timestamped field progress note |
| `GET` | `/api/coordination/notifications` | Public | Query in-app notification feed by audience or responder ID |
| `POST` | `/api/coordination/notifications/{id}/approve` | `X-Operator-Key` | Human operator approval gate for public emergency advisories |

---

## 5. Frontend Interfaces

1. **🚜 Field Responder Console (`ResponderConsoleView.tsx`)**:
   - Unit switcher (`BBMP_Rapid_Unit_1`, `BBMP_Unit_7`, `BBMP_East_Rescue_2`, `Traffic_Warden_South`).
   - "Assigned to My Unit Only" toggle and status chips.
   - Priority badges with expandable deterministic score breakdown.
   - Quick progress notes logging.
   - Expandable resolution drawer with completion notes and photographic proof upload.

2. **🔔 Local In-App Notification Centre (`NotificationCentreView.tsx`)**:
   - Local-first feed categorized by audience: Operator, Field Units, Public Advisories.
   - Delivery badges (`Logged Locally`, `Delivered In-App`, `Pending Approval`).
   - Built-in Operator Approval Gate: Public emergency alerts require BBMP operator credentials before delivery.

3. **🛡️ BBMP Operator Dashboard Integration (`OperatorDashboardView.tsx`)**:
   - "🚜 Dispatch Task" action button on every report in the review queue.
   - Pre-populates spot coordinates, report ID, and priority preview.
   - Direct unit dispatch modal.

---

## 6. Verification and Regression Testing

- **Backend Tests**: 86 passing tests in `backend/tests/` across 16 test files.
- **Coordination Tests**: 9 comprehensive automated tests in `backend/tests/test_coordination.py`:
  - Deterministic prioritization calculation and factor validation.
  - Priority preview endpoint.
  - Operator authentication requirements (401 rejection).
  - Task creation and retrieval.
  - Operator task assignment.
  - Responder access control (403 on unassigned unit modification).
  - Invalid state transition rejection (400 on `open` $\rightarrow$ `resolved`).
  - Progress notes logging and photographic resolution evidence.
  - Emergency notification lifecycle and operator approval gate.
- **Frontend Build**: `tsc && vite build` succeeded in 474ms with zero errors.
- **Historical Model Evaluation**: `backend/scripts/evaluate.py` verified identical metrics and 870.0-minute reanalysis lead time without data leakage.

