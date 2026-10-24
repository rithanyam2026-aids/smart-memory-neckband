"""
Tests for Offline Sync Client and Retry Queue.
Verifies:
- Offline queueing when network is down
- Flushes queue successfully when connection is restored
- Downstream syncing of customized labels, reminders, and private area settings
"""

from pathlib import Path
from device.storage import SecureStorage
from device.models import Person, PersonStatus
from device.sync_client import SyncClient
from cloud.database import CloudDatabase
import cloud.server
from cloud.server import sync_upstream, sync_downstream, SyncUpstreamRequest


class MockResponse:
    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


def test_offline_sync_queue_and_retry(tmp_path: Path):
    local_db_path = tmp_path / "local_sync.db"
    cloud_db_path = tmp_path / "cloud_sync.db"

    local_storage = SecureStorage(db_path=local_db_path)
    cloud_database = CloudDatabase(db_path=cloud_db_path)
    cloud.server.db = cloud_database

    ctx = {
        "user_id": "user_01",
        "role": "caregiver",
        "linked_user_id": "user_01",
        "target_user_id": "user_01",
        "display_name": "Nurse Priya"
    }

    # Create un-synced person locally on neckband
    p = Person(
        label="Unknown #1",
        status=PersonStatus.STRANGER,
        visit_count=1,
        sync_status="pending"
    )
    local_storage.save_person(p)

    # 1. Attempt sync to an unreachable URL (simulating offline disconnected neckband)
    offline_client = SyncClient(
        storage=local_storage,
        cloud_url="http://localhost:99999"  # Unreachable
    )
    res = offline_client.sync_upstream_batch()
    assert res["offline_queued"] >= 1

    # Check that item is safely stored in local SQLite sync_queue
    pending_items = local_storage.get_pending_sync_items()
    assert len(pending_items) >= 1
    assert pending_items[0]["endpoint"] == "/api/sync/upstream"

    # 2. When internet becomes available, push upstream through the Cloud API
    def direct_post(url, json=None, headers=None, timeout=None):
        if "/api/sync/upstream" in url:
            req = SyncUpstreamRequest(**json)
            result = sync_upstream(req, ctx=ctx)
            return MockResponse(200, result)
        return MockResponse(404, {"error": "not found"})

    def direct_get(url, headers=None, timeout=None):
        if "/api/sync/downstream" in url:
            result = sync_downstream(ctx=ctx)
            return MockResponse(200, result)
        return MockResponse(404, {"error": "not found"})

    online_client = SyncClient(storage=local_storage, cloud_url="http://localhost:8000")
    online_client.session.post = direct_post
    online_client.session.get = direct_get

    # Flush the retry queue
    flushed = online_client.flush_retry_queue()
    assert flushed == 1
    assert len(local_storage.get_pending_sync_items()) == 0

    # Verify cloud master database received the person
    cloud_people = cloud_database.get_people("user_01")
    assert len(cloud_people) >= 1
    assert cloud_people[0]["label"] == "Unknown #1"

    # 3. Downstream test: Caregiver customises name on the dashboard
    cloud_database.update_person_label_and_relationship(
        "user_01", p.id, label="Ananya", relationship="granddaughter"
    )
    # Caregiver adds a reminder
    cloud_database.upsert_reminder("user_01", {
        "id": "rem_sync_1",
        "title": "Evening Walk",
        "scheduled_time": "17:00",
        "category": "schedule"
    })
    # Caregiver marks a room private
    cloud_database.set_private_area("user_01", is_private=True, changed_by="Nurse Priya", zone_name="Master Bedroom")

    # Neckband performs downstream sync
    downstream_res = online_client.sync_downstream()
    assert downstream_res["updated_people"] >= 1
    assert downstream_res["updated_reminders"] >= 1
    assert downstream_res["updated_private_areas"] >= 1

    # Verify neckband's local SQLite database now reflects the changes offline!
    updated_local_person = local_storage.get_person(p.id)
    assert updated_local_person is not None
    assert updated_local_person.label == "Ananya"
    assert updated_local_person.relationship == "granddaughter"

    local_reminders = local_storage.get_reminders()
    assert any(r.title == "Evening Walk" for r in local_reminders)

    local_private_areas = local_storage.get_private_area_settings()
    assert any(pa.zone_name == "Master Bedroom" and pa.is_private for pa in local_private_areas)
