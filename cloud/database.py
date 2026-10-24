"""
Cloud Master Database for Smart Memory Neckband.
Features:
- SQL Master Storage for all entities (people, sightings, summaries, notes, reminders, alerts, private areas)
- Audit log for private area modifications (who set it and when)
- Role-based isolation (caregiver only sees linked user)
- Multi-dimensional history queries (by date, person, and zone)
"""

from __future__ import annotations
import json
import sqlite3
import time
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple


class CloudDatabase:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (Path(__file__).resolve().parent.parent / "data" / "cloud_master.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # Users & Caregivers
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    role TEXT NOT NULL, /* 'user' or 'caregiver' */
                    pin_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    linked_user_id TEXT
                )
            """)

            # Recognised People
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS people (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    relationship TEXT,
                    status TEXT NOT NULL,
                    visit_count INTEGER NOT NULL,
                    embedding_json TEXT,
                    embedding_sample_count INTEGER NOT NULL,
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    notes TEXT,
                    updated_at REAL NOT NULL
                )
            """)

            # Sightings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sightings (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    person_id TEXT NOT NULL,
                    person_label TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    confidence REAL NOT NULL,
                    zone TEXT,
                    cell_row INTEGER,
                    cell_col INTEGER,
                    is_doubtful INTEGER NOT NULL DEFAULT 0,
                    doubtful_message TEXT
                )
            """)

            # Conversation Summaries
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS summaries (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    person_id TEXT,
                    person_label TEXT,
                    timestamp REAL NOT NULL,
                    transcript TEXT,
                    summary TEXT NOT NULL,
                    importance_score REAL NOT NULL,
                    key_entities_json TEXT,
                    tags_json TEXT
                )
            """)

            # Notes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    reminder_id TEXT,
                    person_id TEXT,
                    date TEXT NOT NULL,
                    content TEXT NOT NULL,
                    author_role TEXT NOT NULL,
                    author_name TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)

            # Reminders
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    scheduled_time TEXT NOT NULL,
                    category TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    spoken INTEGER NOT NULL DEFAULT 0,
                    created_by TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)

            # Emergency Alerts
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    pulse_bpm REAL NOT NULL,
                    motion_status TEXT NOT NULL,
                    location_zone TEXT,
                    cell_row INTEGER,
                    cell_col INTEGER,
                    gps_coords_json TEXT,
                    severity TEXT NOT NULL,
                    resolved INTEGER NOT NULL DEFAULT 0,
                    trigger_reason TEXT NOT NULL
                )
            """)

            # Master Private Area Settings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS private_area_settings (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    zone_name TEXT,
                    cell_row INTEGER,
                    cell_col INTEGER,
                    is_private INTEGER NOT NULL,
                    set_by TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)

            # Audit Log for Private Area Changes (who set it and when)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS private_area_audit_log (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    zone_name TEXT,
                    cell_row INTEGER,
                    cell_col INTEGER,
                    is_private INTEGER NOT NULL,
                    changed_by TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    notes TEXT
                )
            """)

            # Privacy State Machine Logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS privacy_logs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    state TEXT NOT NULL,
                    is_inside INTEGER NOT NULL,
                    zone TEXT,
                    cell_row INTEGER,
                    cell_col INTEGER,
                    reason TEXT NOT NULL
                )
            """)

            # Device Status Telemetry
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS device_status (
                    device_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    battery_pct REAL NOT NULL,
                    privacy_state TEXT NOT NULL,
                    is_inside INTEGER NOT NULL,
                    current_zone TEXT,
                    cell_row INTEGER,
                    cell_col INTEGER,
                    last_heartbeat REAL NOT NULL,
                    camera_active INTEGER NOT NULL,
                    mic_active INTEGER NOT NULL,
                    sensors_active INTEGER NOT NULL
                )
            """)

            # Insert default users if empty
            cursor.execute("SELECT COUNT(*) as cnt FROM users")
            if cursor.fetchone()["cnt"] == 0:
                # Default User
                cursor.execute("""
                    INSERT INTO users (id, username, role, pin_hash, display_name, linked_user_id)
                    VALUES ('user_01', 'elder_user', 'user', '0000', 'Senior Resident (User)', NULL)
                """)
                # Default Caregiver linked to user_01
                cursor.execute("""
                    INSERT INTO users (id, username, role, pin_hash, display_name, linked_user_id)
                    VALUES ('caregiver_01', 'caregiver_priya', 'caregiver', '1234', 'Nurse Priya (Caregiver)', 'user_01')
                """)

            conn.commit()

    # --- People Management ---
    def upsert_person(self, user_id: str, person_data: Dict[str, Any]):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            emb_json = json.dumps(person_data.get("embedding", []))
            cursor.execute("""
                INSERT OR REPLACE INTO people (
                    id, user_id, label, relationship, status, visit_count,
                    embedding_json, embedding_sample_count, first_seen,
                    last_seen, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                person_data["id"], user_id, person_data["label"],
                person_data.get("relationship"), person_data.get("status", "stranger"),
                person_data.get("visit_count", 1), emb_json,
                person_data.get("embedding_sample_count", 1),
                person_data.get("first_seen", time.time()),
                person_data.get("last_seen", time.time()),
                person_data.get("notes"), time.time()
            ))
            conn.commit()

    def get_people(self, user_id: str) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM people WHERE user_id = ? ORDER BY last_seen DESC", (user_id,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def update_person_label_and_relationship(
        self, user_id: str, person_id: str, label: str, relationship: Optional[str]
    ):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE people
                SET label = ?, relationship = ?, status = 'known', updated_at = ?
                WHERE id = ? AND user_id = ?
            """, (label, relationship, time.time(), person_id, user_id))
            conn.commit()

    # --- Sightings & Summaries History with Filtering ---
    def insert_sighting(self, user_id: str, sighting: Dict[str, Any]):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cell = sighting.get("grid_cell")
            r = cell[0] if cell else sighting.get("cell_row")
            c = cell[1] if cell else sighting.get("cell_col")
            cursor.execute("""
                INSERT OR REPLACE INTO sightings (
                    id, user_id, person_id, person_label, timestamp,
                    confidence, zone, cell_row, cell_col, is_doubtful, doubtful_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sighting["id"], user_id, sighting["person_id"],
                sighting["person_label"], sighting["timestamp"],
                sighting["confidence"], sighting.get("zone"),
                r, c, 1 if sighting.get("is_doubtful") else 0,
                sighting.get("doubtful_message")
            ))
            conn.commit()

    def query_sightings(
        self,
        user_id: str,
        date_str: Optional[str] = None,  # YYYY-MM-DD
        person_query: Optional[str] = None,
        zone: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM sightings WHERE user_id = ?"
            params: List[Any] = [user_id]

            if date_str:
                # Convert YYYY-MM-DD to start & end timestamp
                try:
                    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                    start_ts = dt.replace(tzinfo=datetime.timezone.utc).timestamp()
                    end_ts = start_ts + 86400
                    query += " AND timestamp >= ? AND timestamp < ?"
                    params.extend([start_ts, end_ts])
                except ValueError:
                    pass

            if person_query:
                query += " AND (person_label LIKE ? OR person_id = ?)"
                params.extend([f"%{person_query}%", person_query])

            if zone and zone != "All":
                query += " AND zone = ?"
                params.append(zone)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def insert_summary(self, user_id: str, summary: Dict[str, Any]):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO summaries (
                    id, user_id, person_id, person_label, timestamp,
                    transcript, summary, importance_score, key_entities_json, tags_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                summary["id"], user_id, summary.get("person_id"),
                summary.get("person_label"), summary.get("timestamp", time.time()),
                summary.get("transcript"), summary["summary"],
                summary.get("importance_score", 0.0),
                json.dumps(summary.get("key_entities", {})),
                json.dumps(summary.get("tags", []))
            ))
            conn.commit()

    def query_summaries(
        self,
        user_id: str,
        date_str: Optional[str] = None,
        person_query: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM summaries WHERE user_id = ?"
            params: List[Any] = [user_id]

            if date_str:
                try:
                    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                    start_ts = dt.replace(tzinfo=datetime.timezone.utc).timestamp()
                    end_ts = start_ts + 86400
                    query += " AND timestamp >= ? AND timestamp < ?"
                    params.extend([start_ts, end_ts])
                except ValueError:
                    pass

            if person_query:
                query += " AND (person_label LIKE ? OR person_id = ?)"
                params.extend([f"%{person_query}%", person_query])

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["key_entities"] = json.loads(item.get("key_entities_json") or "{}")
                item["tags"] = json.loads(item.get("tags_json") or "[]")
                results.append(item)
            return results

    # --- Notes CRUD ---
    def insert_note(self, user_id: str, note_data: Dict[str, Any]):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO notes (
                    id, user_id, reminder_id, person_id, date,
                    content, author_role, author_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                note_data["id"], user_id, note_data.get("reminder_id"),
                note_data.get("person_id"), note_data.get("date", datetime.date.today().isoformat()),
                note_data["content"], note_data.get("author_role", "user"),
                note_data.get("author_name", "User"), note_data.get("created_at", time.time())
            ))
            conn.commit()

    def get_notes(self, user_id: str, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM notes WHERE user_id = ?"
            params: List[Any] = [user_id]
            if date_str:
                query += " AND date = ?"
                params.append(date_str)
            query += " ORDER BY created_at DESC"
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    # --- Reminders CRUD ---
    def upsert_reminder(self, user_id: str, reminder_data: Dict[str, Any]):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO reminders (
                    id, user_id, title, description, scheduled_time,
                    category, is_active, spoken, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                reminder_data["id"], user_id, reminder_data["title"],
                reminder_data.get("description"), reminder_data["scheduled_time"],
                reminder_data.get("category", "medication"),
                1 if reminder_data.get("is_active", True) else 0,
                1 if reminder_data.get("spoken", False) else 0,
                reminder_data.get("created_by", "caregiver"),
                reminder_data.get("created_at", time.time())
            ))
            conn.commit()

    def get_reminders(self, user_id: str) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reminders WHERE user_id = ? ORDER BY scheduled_time ASC", (user_id,))
            return [dict(r) for r in cursor.fetchall()]

    def delete_reminder(self, user_id: str, reminder_id: str):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id))
            conn.commit()

    # --- Emergency Alerts ---
    def insert_alert(self, user_id: str, alert_data: Dict[str, Any]):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cell = alert_data.get("grid_cell")
            r = cell[0] if cell else alert_data.get("cell_row")
            c = cell[1] if cell else alert_data.get("cell_col")
            gps_json = json.dumps(alert_data.get("gps_coords")) if alert_data.get("gps_coords") else None

            cursor.execute("""
                INSERT OR REPLACE INTO alerts (
                    id, user_id, timestamp, pulse_bpm, motion_status,
                    location_zone, cell_row, cell_col, gps_coords_json,
                    severity, resolved, trigger_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                alert_data["id"], user_id, alert_data["timestamp"],
                alert_data["pulse_bpm"], alert_data["motion_status"],
                alert_data.get("location_zone"), r, c, gps_json,
                alert_data.get("severity", "CRITICAL"),
                1 if alert_data.get("resolved") else 0,
                alert_data["trigger_reason"]
            ))
            conn.commit()

    def get_alerts(self, user_id: str) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM alerts WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
            return [dict(r) for r in cursor.fetchall()]

    # --- Private Areas & Audit Log ---
    def set_private_area(
        self,
        user_id: str,
        is_private: bool,
        changed_by: str,
        zone_name: Optional[str] = None,
        cell_row: Optional[int] = None,
        cell_col: Optional[int] = None
    ):
        setting_id = f"pa_{zone_name or f'{cell_row}_{cell_col}'}_{user_id}"
        audit_id = f"aud_{int(time.time()*1000)}"
        now = time.time()

        with self._get_conn() as conn:
            cursor = conn.cursor()
            # Upsert setting
            cursor.execute("""
                INSERT OR REPLACE INTO private_area_settings (
                    id, user_id, zone_name, cell_row, cell_col, is_private, set_by, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (setting_id, user_id, zone_name, cell_row, cell_col, 1 if is_private else 0, changed_by, now))

            # Record in Audit Log
            cursor.execute("""
                INSERT INTO private_area_audit_log (
                    id, user_id, zone_name, cell_row, cell_col, is_private, changed_by, timestamp, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                audit_id, user_id, zone_name, cell_row, cell_col,
                1 if is_private else 0, changed_by, now,
                f"Marked {'Private' if is_private else 'Normal'} by {changed_by}"
            ))
            conn.commit()

    def get_private_area_settings(self, user_id: str) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM private_area_settings WHERE user_id = ? ORDER BY updated_at DESC", (user_id,))
            return [dict(r) for r in cursor.fetchall()]

    def get_private_area_audit_log(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM private_area_audit_log WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?", (user_id, limit))
            return [dict(r) for r in cursor.fetchall()]

    # --- Device Status & Privacy Logs ---
    def update_device_status(self, user_id: str, status_data: Dict[str, Any]):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cell = status_data.get("grid_cell")
            r = cell[0] if cell else status_data.get("cell_row")
            c = cell[1] if cell else status_data.get("cell_col")
            cursor.execute("""
                INSERT OR REPLACE INTO device_status (
                    device_id, user_id, battery_pct, privacy_state,
                    is_inside, current_zone, cell_row, cell_col,
                    last_heartbeat, camera_active, mic_active, sensors_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                status_data.get("device_id", "neckband-01"), user_id,
                status_data.get("battery_pct", 95.0),
                status_data.get("privacy_state", "SLEEP"),
                1 if status_data.get("is_inside", True) else 0,
                status_data.get("current_zone", "Living Room"),
                r, c, status_data.get("timestamp", time.time()),
                1 if status_data.get("camera_active") else 0,
                1 if status_data.get("mic_active") else 0,
                1 if status_data.get("sensors_active", True) else 0
            ))
            conn.commit()

    def get_device_status(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM device_status WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return {
                "device_id": "neckband-01",
                "user_id": user_id,
                "battery_pct": 98.0,
                "privacy_state": "SLEEP",
                "is_inside": 1,
                "current_zone": "Living Room",
                "cell_row": 4,
                "cell_col": 2,
                "last_heartbeat": time.time(),
                "camera_active": 0,
                "mic_active": 0,
                "sensors_active": 1
            }

    def insert_privacy_log(self, user_id: str, log_data: Dict[str, Any]):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO privacy_logs (
                    id, user_id, timestamp, state, is_inside, zone, cell_row, cell_col, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log_data["id"], user_id, log_data["timestamp"],
                log_data["state"], 1 if log_data.get("is_inside") else 0,
                log_data.get("zone"), log_data.get("cell_row"),
                log_data.get("cell_col"), log_data["reason"]
            ))
            conn.commit()

    def get_privacy_logs(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM privacy_logs WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?", (user_id, limit))
            return [dict(r) for r in cursor.fetchall()]
