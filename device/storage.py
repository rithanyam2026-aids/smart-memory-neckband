"""
Secure Local Storage for Smart Memory Neckband.
Features:
- Encrypted storage for sensitive fields (embeddings, transcripts, summaries, notes)
- SQLite database supporting fully offline operations
- Configurable data retention policies (strangers ~30d, conversation notes 1-3mo, emergency data never deleted)
- Complete CRUD for people, sightings, summaries, notes, reminders, alerts, and private area settings.
"""

from __future__ import annotations
import base64
import json
import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from device.config import config
from device.models import (
    Person, PersonStatus, Sighting, ConversationSummary, Note, Reminder,
    EmergencyAlert, PrivateAreaSetting, PrivacyLogEntry, PrivacyState
)


class SecureStorage:
    def __init__(self, db_path: Optional[Path] = None, encryption_key: Optional[str] = None):
        self.db_path = db_path or config.LOCAL_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        raw_key = encryption_key or config.DEVICE_ENCRYPTION_KEY
        self.fernet = self._derive_fernet(raw_key)
        self._init_db()

    def _derive_fernet(self, secret: str) -> Fernet:
        """Derive a safe URL-safe base64 32-byte Fernet key from any input secret."""
        salt = b"smart_neckband_salt_fixed"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        derived = base64.urlsafe_b64encode(kdf.derive(secret.encode("utf-8")))
        return Fernet(derived)

    def _encrypt(self, text: Optional[str]) -> Optional[str]:
        if text is None:
            return None
        return self.fernet.encrypt(text.encode("utf-8")).decode("utf-8")

    def _decrypt(self, cipher_text: Optional[str]) -> Optional[str]:
        if cipher_text is None:
            return None
        try:
            return self.fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
        except Exception:
            return None

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            # People
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS people (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    relationship TEXT,
                    status TEXT NOT NULL,
                    visit_count INTEGER NOT NULL,
                    embedding_cipher TEXT,
                    embedding_sample_count INTEGER NOT NULL,
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    notes_cipher TEXT,
                    sync_status TEXT NOT NULL DEFAULT 'synced'
                )
            """)

            # Sightings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sightings (
                    id TEXT PRIMARY KEY,
                    person_id TEXT NOT NULL,
                    person_label TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    confidence REAL NOT NULL,
                    zone TEXT,
                    cell_row INTEGER,
                    cell_col INTEGER,
                    is_doubtful INTEGER NOT NULL DEFAULT 0,
                    doubtful_message TEXT,
                    sync_status TEXT NOT NULL DEFAULT 'pending'
                )
            """)

            # Summaries
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS summaries (
                    id TEXT PRIMARY KEY,
                    person_id TEXT,
                    person_label TEXT,
                    timestamp REAL NOT NULL,
                    transcript_cipher TEXT,
                    summary_cipher TEXT NOT NULL,
                    importance_score REAL NOT NULL,
                    key_entities_cipher TEXT,
                    tags_json TEXT,
                    sync_status TEXT NOT NULL DEFAULT 'pending'
                )
            """)

            # Notes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    reminder_id TEXT,
                    person_id TEXT,
                    date TEXT NOT NULL,
                    content_cipher TEXT NOT NULL,
                    author_role TEXT NOT NULL,
                    author_name TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    sync_status TEXT NOT NULL DEFAULT 'pending'
                )
            """)

            # Reminders
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    scheduled_time TEXT NOT NULL,
                    category TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    spoken INTEGER NOT NULL DEFAULT 0,
                    created_by TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    sync_status TEXT NOT NULL DEFAULT 'synced'
                )
            """)

            # Emergency Alerts - NEVER auto-deleted
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    pulse_bpm REAL NOT NULL,
                    motion_status TEXT NOT NULL,
                    location_zone TEXT,
                    cell_row INTEGER,
                    cell_col INTEGER,
                    gps_coords_json TEXT,
                    severity TEXT NOT NULL,
                    resolved INTEGER NOT NULL DEFAULT 0,
                    trigger_reason TEXT NOT NULL,
                    sync_status TEXT NOT NULL DEFAULT 'pending'
                )
            """)

            # Private Area Settings (zone and cell settings)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS private_area_settings (
                    id TEXT PRIMARY KEY,
                    zone_name TEXT,
                    cell_row INTEGER,
                    cell_col INTEGER,
                    is_private INTEGER NOT NULL,
                    set_by TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)

            # Privacy State Machine Logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS privacy_logs (
                    id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    state TEXT NOT NULL,
                    is_inside INTEGER NOT NULL,
                    zone TEXT,
                    cell_row INTEGER,
                    cell_col INTEGER,
                    reason TEXT NOT NULL,
                    sync_status TEXT NOT NULL DEFAULT 'pending'
                )
            """)

            # Sync Queue for offline retry
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_queue (
                    id TEXT PRIMARY KEY,
                    endpoint TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT
                )
            """)
            conn.commit()

    # --- Person CRUD ---
    def save_person(self, person: Person):
        embedding_json = json.dumps(person.embedding)
        embedding_cipher = self._encrypt(embedding_json)
        notes_cipher = self._encrypt(person.notes)

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO people (
                    id, label, relationship, status, visit_count,
                    embedding_cipher, embedding_sample_count, first_seen,
                    last_seen, notes_cipher, sync_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                person.id, person.label, person.relationship, person.status.value,
                person.visit_count, embedding_cipher, person.embedding_sample_count,
                person.first_seen, person.last_seen, notes_cipher, person.sync_status
            ))
            conn.commit()

    def get_person(self, person_id: str) -> Optional[Person]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM people WHERE id = ?", (person_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_person(row)

    def get_all_people(self) -> List[Person]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM people ORDER BY last_seen DESC")
            rows = cursor.fetchall()
            return [self._row_to_person(r) for r in rows]

    def get_highest_unknown_index(self) -> int:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT label FROM people WHERE label LIKE 'Unknown #%'")
            rows = cursor.fetchall()
            highest = 0
            for r in rows:
                try:
                    num = int(r["label"].replace("Unknown #", "").strip())
                    if num > highest:
                        highest = num
                except ValueError:
                    pass
            return highest

    def _row_to_person(self, row: sqlite3.Row) -> Person:
        emb_json = self._decrypt(row["embedding_cipher"])
        embedding = json.loads(emb_json) if emb_json else []
        notes = self._decrypt(row["notes_cipher"])
        return Person(
            id=row["id"],
            label=row["label"],
            relationship=row["relationship"],
            status=PersonStatus(row["status"]),
            visit_count=row["visit_count"],
            embedding=embedding,
            embedding_sample_count=row["embedding_sample_count"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            notes=notes,
            sync_status=row["sync_status"],
        )

    # --- Sighting CRUD ---
    def save_sighting(self, sighting: Sighting):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cell_row = sighting.grid_cell[0] if sighting.grid_cell else None
            cell_col = sighting.grid_cell[1] if sighting.grid_cell else None
            cursor.execute("""
                INSERT OR REPLACE INTO sightings (
                    id, person_id, person_label, timestamp, confidence,
                    zone, cell_row, cell_col, is_doubtful, doubtful_message, sync_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sighting.id, sighting.person_id, sighting.person_label,
                sighting.timestamp, sighting.confidence, sighting.zone,
                cell_row, cell_col, 1 if sighting.is_doubtful else 0,
                sighting.doubtful_message, sighting.sync_status
            ))
            conn.commit()

    def get_sightings(self, limit: int = 50) -> List[Sighting]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sightings ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                cell = (r["cell_row"], r["cell_col"]) if r["cell_row"] is not None and r["cell_col"] is not None else None
                results.append(Sighting(
                    id=r["id"],
                    person_id=r["person_id"],
                    person_label=r["person_label"],
                    timestamp=r["timestamp"],
                    confidence=r["confidence"],
                    zone=r["zone"],
                    grid_cell=cell,
                    is_doubtful=bool(r["is_doubtful"]),
                    doubtful_message=r["doubtful_message"],
                    sync_status=r["sync_status"],
                ))
            return results

    # --- Conversation Summaries ---
    def save_summary(self, summary: ConversationSummary):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            transcript_cipher = self._encrypt(summary.transcript)
            summary_cipher = self._encrypt(summary.summary)
            entities_cipher = self._encrypt(json.dumps(summary.key_entities))
            tags_json = json.dumps(summary.tags)

            cursor.execute("""
                INSERT OR REPLACE INTO summaries (
                    id, person_id, person_label, timestamp, transcript_cipher,
                    summary_cipher, importance_score, key_entities_cipher,
                    tags_json, sync_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                summary.id, summary.person_id, summary.person_label,
                summary.timestamp, transcript_cipher, summary_cipher,
                summary.importance_score, entities_cipher, tags_json,
                summary.sync_status
            ))
            conn.commit()

    def get_summaries(self, limit: int = 50) -> List[ConversationSummary]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM summaries ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                trans = self._decrypt(r["transcript_cipher"])
                summ = self._decrypt(r["summary_cipher"]) or ""
                ent_str = self._decrypt(r["key_entities_cipher"])
                entities = json.loads(ent_str) if ent_str else {}
                tags = json.loads(r["tags_json"]) if r["tags_json"] else []
                results.append(ConversationSummary(
                    id=r["id"],
                    person_id=r["person_id"],
                    person_label=r["person_label"],
                    timestamp=r["timestamp"],
                    transcript=trans,
                    summary=summ,
                    importance_score=r["importance_score"],
                    key_entities=entities,
                    tags=tags,
                    sync_status=r["sync_status"],
                ))
            return results

    # --- Notes ---
    def save_note(self, note: Note):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            content_cipher = self._encrypt(note.content)
            cursor.execute("""
                INSERT OR REPLACE INTO notes (
                    id, reminder_id, person_id, date, content_cipher,
                    author_role, author_name, created_at, sync_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                note.id, note.reminder_id, note.person_id, note.date,
                content_cipher, note.author_role, note.author_name,
                note.created_at, note.sync_status
            ))
            conn.commit()

    def get_notes(self) -> List[Note]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM notes ORDER BY created_at DESC")
            rows = cursor.fetchall()
            results = []
            for r in rows:
                content = self._decrypt(r["content_cipher"]) or ""
                results.append(Note(
                    id=r["id"],
                    reminder_id=r["reminder_id"],
                    person_id=r["person_id"],
                    date=r["date"],
                    content=content,
                    author_role=r["author_role"],
                    author_name=r["author_name"],
                    created_at=r["created_at"],
                    sync_status=r["sync_status"],
                ))
            return results

    # --- Reminders ---
    def save_reminder(self, reminder: Reminder):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO reminders (
                    id, title, description, scheduled_time, category,
                    is_active, spoken, created_by, created_at, sync_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                reminder.id, reminder.title, reminder.description,
                reminder.scheduled_time, reminder.category,
                1 if reminder.is_active else 0,
                1 if reminder.spoken else 0,
                reminder.created_by, reminder.created_at, reminder.sync_status
            ))
            conn.commit()

    def get_reminders(self, active_only: bool = False) -> List[Reminder]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM reminders"
            if active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY scheduled_time ASC"
            cursor.execute(query)
            rows = cursor.fetchall()
            return [
                Reminder(
                    id=r["id"],
                    title=r["title"],
                    description=r["description"],
                    scheduled_time=r["scheduled_time"],
                    category=r["category"],
                    is_active=bool(r["is_active"]),
                    spoken=bool(r["spoken"]),
                    created_by=r["created_by"],
                    created_at=r["created_at"],
                    sync_status=r["sync_status"],
                )
                for r in rows
            ]

    def mark_reminder_spoken(self, reminder_id: str):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE reminders SET spoken = 1 WHERE id = ?", (reminder_id,))
            conn.commit()

    # --- Emergency Alerts (Never auto-purged) ---
    def save_alert(self, alert: EmergencyAlert):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cell_row = alert.grid_cell[0] if alert.grid_cell else None
            cell_col = alert.grid_cell[1] if alert.grid_cell else None
            gps_json = json.dumps(alert.gps_coords) if alert.gps_coords else None

            cursor.execute("""
                INSERT OR REPLACE INTO alerts (
                    id, timestamp, pulse_bpm, motion_status, location_zone,
                    cell_row, cell_col, gps_coords_json, severity, resolved,
                    trigger_reason, sync_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                alert.id, alert.timestamp, alert.pulse_bpm, alert.motion_status,
                alert.location_zone, cell_row, cell_col, gps_json,
                alert.severity, 1 if alert.resolved else 0, alert.trigger_reason,
                alert.sync_status
            ))
            conn.commit()

    def get_alerts(self) -> List[EmergencyAlert]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM alerts ORDER BY timestamp DESC")
            rows = cursor.fetchall()
            results = []
            for r in rows:
                cell = (r["cell_row"], r["cell_col"]) if r["cell_row"] is not None and r["cell_col"] is not None else None
                gps = json.loads(r["gps_coords_json"]) if r["gps_coords_json"] else None
                results.append(EmergencyAlert(
                    id=r["id"],
                    timestamp=r["timestamp"],
                    pulse_bpm=r["pulse_bpm"],
                    motion_status=r["motion_status"],
                    location_zone=r["location_zone"],
                    grid_cell=cell,
                    gps_coords=gps,
                    severity=r["severity"],
                    resolved=bool(r["resolved"]),
                    trigger_reason=r["trigger_reason"],
                    sync_status=r["sync_status"],
                ))
            return results

    # --- Private Area Settings ---
    def save_private_area_setting(self, setting: PrivateAreaSetting):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO private_area_settings (
                    id, zone_name, cell_row, cell_col, is_private, set_by, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                setting.id, setting.zone_name, setting.cell_row, setting.cell_col,
                1 if setting.is_private else 0, setting.set_by, setting.updated_at
            ))
            conn.commit()

    def get_private_area_settings(self) -> List[PrivateAreaSetting]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM private_area_settings ORDER BY updated_at DESC")
            rows = cursor.fetchall()
            return [
                PrivateAreaSetting(
                    id=r["id"],
                    zone_name=r["zone_name"],
                    cell_row=r["cell_row"],
                    cell_col=r["cell_col"],
                    is_private=bool(r["is_private"]),
                    set_by=r["set_by"],
                    updated_at=r["updated_at"]
                )
                for r in rows
            ]

    # --- Privacy Logs ---
    def save_privacy_log(self, entry: PrivacyLogEntry):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO privacy_logs (
                    id, timestamp, state, is_inside, zone, cell_row, cell_col, reason, sync_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.id, entry.timestamp, entry.state.value, 1 if entry.is_inside else 0,
                entry.zone, entry.cell_row, entry.cell_col, entry.reason, entry.sync_status
            ))
            conn.commit()

    def get_privacy_logs(self, limit: int = 100) -> List[PrivacyLogEntry]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM privacy_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [
                PrivacyLogEntry(
                    id=r["id"],
                    timestamp=r["timestamp"],
                    state=PrivacyState(r["state"]),
                    is_inside=bool(r["is_inside"]),
                    zone=r["zone"],
                    cell_row=r["cell_row"],
                    cell_col=r["cell_col"],
                    reason=r["reason"],
                    sync_status=r["sync_status"],
                )
                for r in rows
            ]

    # --- Sync Queue ---
    def enqueue_sync(self, endpoint: str, payload: Dict[str, Any]) -> str:
        queue_id = f"q_{int(time.time()*1000)}_{sqlite3.connect(':memory:').total_changes}"
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_queue (id, endpoint, payload_json, created_at, retry_count)
                VALUES (?, ?, ?, ?, 0)
            """, (queue_id, endpoint, json.dumps(payload), time.time()))
            conn.commit()
        return queue_id

    def get_pending_sync_items(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sync_queue ORDER BY created_at ASC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [
                {
                    "id": r["id"],
                    "endpoint": r["endpoint"],
                    "payload": json.loads(r["payload_json"]),
                    "created_at": r["created_at"],
                    "retry_count": r["retry_count"],
                    "last_error": r["last_error"],
                }
                for r in rows
            ]

    def remove_sync_item(self, item_id: str):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sync_queue WHERE id = ?", (item_id,))
            conn.commit()

    def update_sync_retry(self, item_id: str, error_msg: str):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sync_queue
                SET retry_count = retry_count + 1, last_error = ?
                WHERE id = ?
            """, (error_msg, item_id))
            conn.commit()

    # --- Time-Limited Data Retention Engine ---
    def run_retention_cleanup(
        self,
        current_time: Optional[float] = None,
        stranger_days: int = 30,
        notes_days: int = 60
    ) -> Dict[str, int]:
        """
        Enforce privacy retention rules:
        - Delete strangers not seen in stranger_days (~30 days).
        - Familiar/known contacts NEVER deleted by time retention.
        - Delete conversation summaries and notes older than notes_days (1-3 months).
        - NEVER auto-delete emergency alerts.
        """
        now = current_time or time.time()
        stranger_cutoff = now - (stranger_days * 86400)
        notes_cutoff = now - (notes_days * 86400)

        deleted_strangers = 0
        deleted_summaries = 0
        deleted_notes = 0

        with self._get_conn() as conn:
            cursor = conn.cursor()
            # 1. Delete expired strangers (NOT familiar, NOT known)
            cursor.execute("""
                DELETE FROM people
                WHERE status = 'stranger' AND last_seen < ?
            """, (stranger_cutoff,))
            deleted_strangers = cursor.rowcount

            # 2. Delete expired summaries
            cursor.execute("""
                DELETE FROM summaries
                WHERE timestamp < ?
            """, (notes_cutoff,))
            deleted_summaries = cursor.rowcount

            # 3. Delete expired notes
            cursor.execute("""
                DELETE FROM notes
                WHERE created_at < ?
            """, (notes_cutoff,))
            deleted_notes = cursor.rowcount

            conn.commit()

        return {
            "deleted_strangers": deleted_strangers,
            "deleted_summaries": deleted_summaries,
            "deleted_notes": deleted_notes,
        }
