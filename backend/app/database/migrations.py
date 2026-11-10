"""Lightweight schema migration runner for FloodSense AI SQLite database.

Tracks PRAGMA user_version and applies incremental DDL migrations transactionally.
Automatically runs upon server initialization.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.database.db import get_connection

LATEST_VERSION = 3

MIGRATION_V1 = """
-- 1. Citizen Flood & Control Reports
CREATE TABLE IF NOT EXISTS citizen_reports (
    report_id TEXT PRIMARY KEY,
    spot_id TEXT NOT NULL,
    report_type TEXT NOT NULL CHECK (report_type IN ('flood', 'control_clear')),
    water_depth_cm REAL,
    severity INTEGER CHECK (severity IN (1, 2, 3, 4)),
    severity_level TEXT DEFAULT 'medium' CHECK (severity_level IN ('low', 'medium', 'high', 'critical')),
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    image_filename TEXT,
    reporter_alias TEXT DEFAULT 'Anonymous Citizen',
    verification_status TEXT NOT NULL DEFAULT 'submitted' CHECK (verification_status IN ('submitted', 'under_review', 'approved', 'rejected', 'needs_info', 'pending', 'verified')),
    verified_at TEXT,
    verified_by TEXT,
    notes TEXT,
    duplicate_of_id TEXT,
    decision_reason TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_spot ON citizen_reports(spot_id, created_at);
CREATE INDEX IF NOT EXISTS idx_reports_status ON citizen_reports(verification_status);
CREATE INDEX IF NOT EXISTS idx_reports_duplicate ON citizen_reports(duplicate_of_id);

-- 2. Municipal Dewatering & Barricade Dispatch Directives
CREATE TABLE IF NOT EXISTS municipal_dispatches (
    dispatch_id TEXT PRIMARY KEY,
    spot_id TEXT NOT NULL,
    report_id TEXT,
    directive_type TEXT NOT NULL CHECK (directive_type IN ('pump_deployment', 'barricade_order', 'traffic_diversion')),
    priority TEXT NOT NULL CHECK (priority IN ('P1_CRITICAL', 'P2_ELEVATED', 'P3_ROUTINE')),
    status TEXT NOT NULL DEFAULT 'ordered' CHECK (status IN ('ordered', 'en_route', 'active', 'demobilized')),
    location_name TEXT NOT NULL,
    capacity_gpm TEXT,
    action_instructions TEXT NOT NULL,
    assigned_team TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(report_id) REFERENCES citizen_reports(report_id)
);

CREATE INDEX IF NOT EXISTS idx_dispatch_status ON municipal_dispatches(status);

-- 3. Audit Log for Response Actions
CREATE TABLE IF NOT EXISTS response_audit_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    actor_role TEXT NOT NULL CHECK (actor_role IN ('citizen', 'municipal_operator', 'system_agent')),
    details_json TEXT NOT NULL
);
"""

MIGRATION_V2 = """
ALTER TABLE citizen_reports ADD COLUMN duplicate_of_id TEXT;
ALTER TABLE citizen_reports ADD COLUMN decision_reason TEXT;
CREATE INDEX IF NOT EXISTS idx_reports_duplicate ON citizen_reports(duplicate_of_id);
"""

MIGRATION_V3 = """
-- 4. Response Coordination Tasks
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

CREATE INDEX IF NOT EXISTS idx_tasks_status ON response_tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_responder ON response_tasks(assigned_responder_id);
CREATE INDEX IF NOT EXISTS idx_tasks_spot ON response_tasks(spot_id);

-- 5. Task Progress Notes
CREATE TABLE IF NOT EXISTS task_progress_notes (
    note_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    author_role TEXT NOT NULL CHECK (author_role IN ('operator', 'responder')),
    note TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES response_tasks(task_id)
);

CREATE INDEX IF NOT EXISTS idx_notes_task ON task_progress_notes(task_id);

-- 6. In-App Notifications
CREATE TABLE IF NOT EXISTS in_app_notifications (
    notification_id TEXT PRIMARY KEY,
    task_id TEXT,
    report_id TEXT,
    target_audience TEXT NOT NULL CHECK (target_audience IN ('operator', 'responder', 'public_advisory')),
    target_responder_id TEXT,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    delivery_status TEXT NOT NULL DEFAULT 'logged_locally' CHECK (delivery_status IN ('logged_locally', 'delivered_in_app', 'acknowledged', 'pending_approval')),
    requires_human_approval INTEGER DEFAULT 0,
    approved_by TEXT,
    approved_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notif_audience ON in_app_notifications(target_audience);
CREATE INDEX IF NOT EXISTS idx_notif_responder ON in_app_notifications(target_responder_id);
"""


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Applies pending migrations up to LATEST_VERSION."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version;")
    current_version = cursor.fetchone()[0]

    if current_version < 1:
        cursor.executescript(MIGRATION_V1)
        cursor.executescript(MIGRATION_V3)
        cursor.execute("PRAGMA user_version = 3;")
        conn.commit()
        return 3

    if current_version < 2:
        try:
            cursor.executescript(MIGRATION_V2)
        except sqlite3.OperationalError:
            pass
        cursor.execute("PRAGMA user_version = 2;")
        conn.commit()
        current_version = 2

    if current_version < 3:
        cursor.executescript(MIGRATION_V3)
        cursor.execute("PRAGMA user_version = 3;")
        conn.commit()
        current_version = 3

    return current_version


def run_startup_migrations(db_path: Path | str | None = None) -> int:
    """Helper called on app startup."""
    conn = get_connection(db_path)
    try:
        ver = apply_migrations(conn)
        return ver
    finally:
        conn.close()
