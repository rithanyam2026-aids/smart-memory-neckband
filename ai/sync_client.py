"""
Offline-First Cloud Sync Client for Python AI Service.
Syncs with Cloud backend and pushes downstream updates to ESP32 Neckband over local link.
"""

from __future__ import annotations
import logging
import time
from typing import Dict, Any, Optional
import requests

from ai.config import config
from ai.storage import SecureStorage
from ai.models import Person, PersonStatus, Reminder, PrivateAreaSetting

logger = logging.getLogger("AISyncClient")


class AISyncClient:
    def __init__(
        self,
        storage: SecureStorage,
        cloud_url: Optional[str] = None,
        auth_token: Optional[str] = None
    ):
        self.storage = storage
        self.cloud_url = cloud_url or config.CLOUD_API_URL
        self.auth_token = auth_token
        self.session = requests.Session()

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def sync_upstream_batch(self, max_items: int = 50) -> Dict[str, int]:
        people = [p.model_dump() for p in self.storage.get_all_people() if p.sync_status == "pending"]
        sightings = [s.model_dump() for s in self.storage.get_sightings(limit=max_items) if s.sync_status == "pending"]
        summaries = [sm.model_dump() for sm in self.storage.get_summaries(limit=max_items) if sm.sync_status == "pending"]
        notes = [n.model_dump() for n in self.storage.get_notes() if n.sync_status == "pending"]
        alerts = [a.model_dump() for a in self.storage.get_alerts() if a.sync_status == "pending"]
        privacy_logs = [l.model_dump() for l in self.storage.get_privacy_logs(limit=max_items) if l.sync_status == "pending"]

        total_pending = len(people) + len(sightings) + len(summaries) + len(notes) + len(alerts) + len(privacy_logs)
        if total_pending == 0:
            return {"synced": 0, "offline_queued": 0}

        payload = {
            "people": people,
            "sightings": sightings,
            "summaries": summaries,
            "notes": notes,
            "alerts": alerts,
            "privacy_logs": privacy_logs,
        }

        try:
            url = f"{self.cloud_url}/api/sync/upstream"
            resp = self.session.post(url, json=payload, headers=self._headers(), timeout=4.0)
            if resp.status_code == 200:
                self._mark_local_items_synced(people, sightings, summaries, notes, alerts, privacy_logs)
                return {"synced": total_pending, "offline_queued": 0}
            else:
                self.storage.enqueue_sync("/api/sync/upstream", payload)
                return {"synced": 0, "offline_queued": total_pending}
        except Exception:
            self.storage.enqueue_sync("/api/sync/upstream", payload)
            return {"synced": 0, "offline_queued": total_pending}

    def sync_downstream(self) -> Dict[str, Any]:
        try:
            url = f"{self.cloud_url}/api/sync/downstream"
            resp = self.session.get(url, headers=self._headers(), timeout=4.0)
            if resp.status_code != 200:
                return {"error": resp.status_code}

            data = resp.json()
            updated_people = 0
            updated_reminders = 0
            private_zones = []
            private_cells = []

            for p_dict in data.get("people", []):
                local_person = self.storage.get_person(p_dict["id"])
                if local_person:
                    if p_dict.get("label"): local_person.label = p_dict["label"]
                    if p_dict.get("relationship"): local_person.relationship = p_dict["relationship"]
                    if p_dict.get("status"): local_person.status = PersonStatus(p_dict["status"])
                    self.storage.save_person(local_person)
                    updated_people += 1

            for r_dict in data.get("reminders", []):
                reminder = Reminder(
                    id=r_dict["id"],
                    title=r_dict["title"],
                    description=r_dict.get("description"),
                    scheduled_time=r_dict["scheduled_time"],
                    category=r_dict.get("category", "medication"),
                    is_active=bool(r_dict.get("is_active", True)),
                    spoken=bool(r_dict.get("spoken", False)),
                    created_by=r_dict.get("created_by", "caregiver")
                )
                self.storage.save_reminder(reminder)
                updated_reminders += 1

            for pa_dict in data.get("private_areas", []):
                setting = PrivateAreaSetting(
                    id=pa_dict["id"],
                    zone_name=pa_dict.get("zone_name"),
                    cell_row=pa_dict.get("cell_row"),
                    cell_col=pa_dict.get("cell_col"),
                    is_private=bool(pa_dict.get("is_private", True)),
                    set_by=pa_dict.get("set_by", "caregiver"),
                    updated_at=pa_dict.get("updated_at", time.time())
                )
                self.storage.save_private_area_setting(setting)
                if setting.is_private:
                    if setting.zone_name: private_zones.append(setting.zone_name)
                    if setting.cell_row is not None and setting.cell_col is not None:
                        private_cells.append([setting.cell_row, setting.cell_col])

            return {
                "updated_people": updated_people,
                "updated_reminders": updated_reminders,
                "neckband_settings_payload": {
                    "private_zones": private_zones,
                    "private_cells": private_cells,
                }
            }
        except Exception as e:
            return {"error": str(e)}

    def _mark_local_items_synced(self, people, sightings, summaries, notes, alerts, privacy_logs):
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            for p in people:
                cursor.execute("UPDATE people SET sync_status = 'synced' WHERE id = ?", (p["id"],))
            for s in sightings:
                cursor.execute("UPDATE sightings SET sync_status = 'synced' WHERE id = ?", (s["id"],))
            for sm in summaries:
                cursor.execute("UPDATE summaries SET sync_status = 'synced' WHERE id = ?", (sm["id"],))
            for n in notes:
                cursor.execute("UPDATE notes SET sync_status = 'synced' WHERE id = ?", (n["id"],))
            for a in alerts:
                cursor.execute("UPDATE alerts SET sync_status = 'synced' WHERE id = ?", (a["id"],))
            for l in privacy_logs:
                cursor.execute("UPDATE privacy_logs SET sync_status = 'synced' WHERE id = ?", (l["id"],))
            conn.commit()
