"""Demo data seeder for FloodSense AI hackathon presentations.

Populates realistic Bengaluru citizen reports, municipal review items,
operational evidence signals, response tasks, and emergency notifications
to enable an instant, high-impact live demonstration.

Usage:
    PYTHONPATH=backend python3 backend/scripts/seed_demo_data.py
"""
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.database.db import get_db
from app.database.migrations import run_startup_migrations
from app.demo.fixtures import SPOTS

SPOTS_BY_ID = {s.id: s for s in SPOTS}


def seed_demo_data():
    print("Initializing SQLite database & running migrations...")
    run_startup_migrations()

    now = datetime.now(timezone.utc)
    t_minus_15m = (now - timedelta(minutes=15)).isoformat(timespec="seconds")
    t_minus_45m = (now - timedelta(minutes=45)).isoformat(timespec="seconds")
    t_minus_2h = (now - timedelta(hours=2)).isoformat(timespec="seconds")
    now_iso = now.isoformat(timespec="seconds")

    with get_db() as conn:
        cursor = conn.cursor()

        # ----------------------------------------------------------------------
        # 1. Citizen Flood & Control Reports
        # ----------------------------------------------------------------------
        print("Seeding realistic citizen reports...")

        # Report 1: Critical incident at KR Circle (Pending review - perfect for live operator demo)
        rep1_id = "rep_krc_live_01"
        cursor.execute(
            """
            INSERT OR REPLACE INTO citizen_reports (
                report_id, spot_id, report_type, water_depth_cm, severity, severity_level,
                latitude, longitude, reporter_alias, verification_status, notes, created_at
            ) VALUES (?, ?, 'flood', 85.0, 4, 'critical', 12.9763, 77.5929, 'Citizen_CubbonPark', 'submitted',
                      'K.R. Circle underpass submerged after heavy downpour. Two cars stranded. Sump overflow active.', ?)
            """,
            (rep1_id, "kr_circle", t_minus_15m),
        )

        # Report 2: Near KR Circle - Potential Duplicate (demonstrates spatial duplicate clustering)
        rep2_id = "rep_krc_dup_02"
        cursor.execute(
            """
            INSERT OR REPLACE INTO citizen_reports (
                report_id, spot_id, report_type, water_depth_cm, severity, severity_level,
                latitude, longitude, reporter_alias, verification_status, notes, created_at
            ) VALUES (?, ?, 'flood', 75.0, 4, 'critical', 12.9768, 77.5932, 'AutoDriver_Central', 'submitted',
                      'Heavy water accumulation near north approach ramp. Traffic halted.', ?)
            """,
            (rep2_id, "kr_circle", now_iso),
        )

        # Report 3: Silk Board Junction (Already Approved - highlights live Evidence Overlay)
        rep3_id = "rep_silk_app_03"
        cursor.execute(
            """
            INSERT OR REPLACE INTO citizen_reports (
                report_id, spot_id, report_type, water_depth_cm, severity, severity_level,
                latitude, longitude, reporter_alias, verification_status, verified_at, verified_by,
                decision_reason, notes, created_at
            ) VALUES (?, ?, 'flood', 45.0, 3, 'high', 12.9177, 77.6233, 'TechPark_Commuter', 'approved',
                      ?, 'Duty_Officer_South', 'Corroborated by Traffic Police CCTV camera 08.',
                      'Waterlogging along service road towards Madiwala. Slow-moving traffic.', ?)
            """,
            (rep3_id, "silk_board", t_minus_45m, t_minus_2h),
        )

        # Report 4: Hebbal Flyover (Verified Clear Pass - demonstrates true negative crowd controls)
        rep4_id = "rep_hebbal_clr_04"
        cursor.execute(
            """
            INSERT OR REPLACE INTO citizen_reports (
                report_id, spot_id, report_type, water_depth_cm, severity, severity_level,
                latitude, longitude, reporter_alias, verification_status, verified_at, verified_by,
                decision_reason, notes, created_at
            ) VALUES (?, ?, 'control_clear', NULL, NULL, NULL, 13.0358, 77.5970, 'Airport_Taxi_Driver', 'approved',
                      ?, 'Control_Desk_North', 'Verified clear by Ward 8巡 inspection team.',
                      'Hebbal flyover ramps and underpasses clear of standing water. Normal traffic flow.', ?)
            """,
            (rep4_id, "hebbal", t_minus_15m, t_minus_45m),
        )

        # ----------------------------------------------------------------------
        # 2. Response Tasks & Field Coordination
        # ----------------------------------------------------------------------
        print("Seeding civic response tasks...")

        # Task 1: High-Volume Dewatering at Silk Board (Assigned to BBMP Unit 7)
        task1_id = "task_sb_pump_01"
        prio_reasons_1 = {
            "calculated_priority": "P1_CRITICAL",
            "total_score": 75,
            "factors": [
                {"factor": "incident_severity", "points": 30, "reason": "High severity waterlogging (45cm observed depth)"},
                {"factor": "nearby_corroboration", "points": 10, "reason": "1 human-verified citizen report in proximity"},
                {"factor": "evidence_freshness", "points": 20, "reason": "Fresh verified evidence filed within past 2 hours"},
                {"factor": "location_criticality", "points": 15, "reason": "Critical underpass depression (Silk Board Junction, rel_depth=4.5m)"},
            ],
            "explanation": "P1_CRITICAL assigned with score 75/100 based on verified depth, freshness, and high physical depression vulnerability.",
        }

        due_time_1 = (now + timedelta(hours=1, minutes=30)).isoformat(timespec="seconds")
        cursor.execute(
            """
            INSERT OR REPLACE INTO response_tasks (
                task_id, incident_report_id, spot_id, location_name, latitude, longitude,
                title, description, priority, priority_reasons_json, assigned_responder_id,
                assigned_by, status, due_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 12.9177, 77.6233, ?, ?, 'P1_CRITICAL', ?, 'BBMP_Unit_7',
                      'BBMP_Central_Control', 'assigned', ?, ?, ?)
            """,
            (
                task1_id,
                rep3_id,
                "silk_board",
                "Silk Board Junction",
                "Deploy High-Volume Diesel Suction Pump at Silk Board",
                "Clear 45cm flood waters along Madiwala service road before evening peak transit.",
                json.dumps(prio_reasons_1),
                due_time_1,
                t_minus_45m,
                t_minus_45m,
            ),
        )

        # Task 2: Bellandur Lake Outflow Sump Desilting (In-Progress by BBMP Rapid Unit 1)
        task2_id = "task_bel_drain_02"
        prio_reasons_2 = {
            "calculated_priority": "P2_HIGH",
            "total_score": 60,
            "factors": [
                {"factor": "incident_severity", "points": 30, "reason": "High severity observed waterlogging"},
                {"factor": "nearby_corroboration", "points": 0, "reason": "Single report on lake fringe"},
                {"factor": "evidence_freshness", "points": 15, "reason": "Active rain nowcast"},
                {"factor": "location_criticality", "points": 15, "reason": "Deepest depression spot (Bellandur, rel_depth=5.5m)"},
            ],
            "explanation": "P2_HIGH assigned with score 60/100.",
        }

        due_time_2 = (now + timedelta(hours=3)).isoformat(timespec="seconds")
        cursor.execute(
            """
            INSERT OR REPLACE INTO response_tasks (
                task_id, spot_id, location_name, latitude, longitude,
                title, description, priority, priority_reasons_json, assigned_responder_id,
                assigned_by, status, due_at, created_at, updated_at
            ) VALUES (?, 'bellandur', 'Bellandur Lake Edge', 12.9352, 77.6745, ?, ?, 'P2_HIGH', ?,
                      'BBMP_Rapid_Unit_1', 'BBMP_Stormwater_Division', 'in_progress', ?, ?, ?)
            """,
            (
                task2_id,
                "Clear Culvert Grating at Bellandur Lake Outflow",
                "Desilt stormwater drainage screens to allow unimpeded outflow into Varthur valley.",
                json.dumps(prio_reasons_2),
                due_time_2,
                t_minus_2h,
                t_minus_15m,
            ),
        )

        # Progress note for Task 2
        cursor.execute(
            """
            INSERT OR REPLACE INTO task_progress_notes (
                note_id, task_id, author_id, author_role, note, created_at
            ) VALUES (9001, ?, 'BBMP_Rapid_Unit_1', 'responder',
                      'Rapid response unit on site. De-silting screen cleared with mechanical rake. Flow restored.', ?)
            """,
            (task2_id, t_minus_15m),
        )

        # ----------------------------------------------------------------------
        # 3. Local In-App Notifications
        # ----------------------------------------------------------------------
        print("Seeding in-app notifications & emergency approval gate...")

        # Notification 1: Public emergency advisory awaiting BBMP operator authorization
        notif1_id = "notif_gate_01"
        cursor.execute(
            """
            INSERT OR REPLACE INTO in_app_notifications (
                notification_id, report_id, target_audience, title, message, severity,
                delivery_status, requires_human_approval, created_at
            ) VALUES (?, ?, 'public_advisory',
                      'FLASH FLOOD ADVISORY: K.R. Circle Underpass Impassable',
                      'K.R. Circle underpass submerged over 80cm. Divert via Cubbon Park / Nrupathunga Road. Do not attempt crossing.',
                      'critical', 'pending_approval', 1, ?)
            """,
            (notif1_id, rep1_id, t_minus_15m),
        )

        # Notification 2: Field responder assignment notification
        notif2_id = "notif_resp_02"
        cursor.execute(
            """
            INSERT OR REPLACE INTO in_app_notifications (
                notification_id, task_id, target_audience, target_responder_id, title, message, severity,
                delivery_status, requires_human_approval, created_at
            ) VALUES (?, ?, 'responder', 'BBMP_Unit_7',
                      'New P1 Critical Task Dispatched',
                      'Unit BBMP_Unit_7 assigned to deploy high-volume diesel pump at Silk Board Junction.',
                      'warning', 'delivered_in_app', 0, ?)
            """,
            (notif2_id, task1_id, t_minus_45m),
        )

        # ----------------------------------------------------------------------
        # 4. Audit Log Entries
        # ----------------------------------------------------------------------
        print("Seeding audit history...")
        audit_events = [
            (t_minus_2h, "citizen_report_created", "citizen", {"report_id": rep3_id, "spot_id": "silk_board"}),
            (t_minus_45m, "citizen_report_verified", "municipal_operator", {"report_id": rep3_id, "action": "approved", "by": "Duty_Officer_South"}),
            (t_minus_45m, "response_task_created", "municipal_operator", {"task_id": task1_id, "priority": "P1_CRITICAL", "assigned_to": "BBMP_Unit_7"}),
            (t_minus_15m, "citizen_report_created", "citizen", {"report_id": rep1_id, "spot_id": "kr_circle"}),
            (t_minus_15m, "response_task_status_updated", "municipal_operator", {"task_id": task2_id, "status": "in_progress", "unit": "BBMP_Rapid_Unit_1"}),
        ]

        for ts, act, role, details in audit_events:
            cursor.execute(
                """
                INSERT INTO response_audit_log (event_timestamp, action, actor_role, details_json)
                VALUES (?, ?, ?, ?)
                """,
                (ts, act, role, json.dumps(details)),
            )

    print("\n✓ Seed completed successfully!")
    print(f"  • Reports: 4 seeded (1 pending KR Circle, 1 duplicate alert, 1 approved Silk Board, 1 clear control)")
    print(f"  • Tasks: 2 seeded (1 P1_CRITICAL at Silk Board, 1 P2_HIGH in-progress at Bellandur)")
    print(f"  • Notifications: 2 seeded (1 pending operator approval gate, 1 delivered to BBMP_Unit_7)")
    print(f"  • Audit Log: 5 entries recorded")


if __name__ == "__main__":
    seed_demo_data()
