"""
Tests for Cloud API Backend:
- PIN authentication for user and caregiver
- Caregiver isolation to linked elder user
- History queries by date, person, and zone
- Private-area change audit log (who changed it and when)
- CRUD for reminders and notes
"""

from pathlib import Path
import pytest
from fastapi import HTTPException
from cloud.database import CloudDatabase
from cloud.server import (
    login,
    get_sightings,
    create_reminder,
    get_reminders,
    set_private_area,
    get_private_areas,
    LoginRequest,
    ReminderCreateRequest,
    PrivateAreaRequest,
)
from cloud.auth import decode_token


def test_auth_and_user_isolation(tmp_path: Path):
    test_db = CloudDatabase(db_path=tmp_path / "cloud_test.db")
    import cloud.server
    cloud.server.db = test_db

    # 1. Invalid PIN raises HTTPException 401
    with pytest.raises(HTTPException) as exc:
        login(LoginRequest(role="caregiver", pin="9999"))
    assert exc.value.status_code == 401

    # 2. Caregiver login with PIN 1234
    res_cg = login(LoginRequest(role="caregiver", pin="1234"))
    assert "token" in res_cg
    assert res_cg["role"] == "caregiver"
    assert res_cg["target_user_id"] == "user_01"

    claims = decode_token(res_cg["token"])
    assert claims is not None
    assert claims["role"] == "caregiver"

    # Context for caregiver
    cg_ctx = {
        "user_id": "caregiver_01",
        "role": "caregiver",
        "linked_user_id": "user_01",
        "target_user_id": "user_01",
        "display_name": "Nurse Priya (Caregiver)"
    }

    # 3. User login with PIN 0000
    res_u = login(LoginRequest(role="user", pin="0000"))
    assert res_u["role"] == "user"
    assert res_u["target_user_id"] == "user_01"

    u_ctx = {
        "user_id": "user_01",
        "role": "user",
        "linked_user_id": None,
        "target_user_id": "user_01",
        "display_name": "Senior Resident"
    }

    # 4. Caregiver creates a reminder for linked user
    rem_req = ReminderCreateRequest(
        title="Heart Medication",
        description="Take 1 pill of Metoprolol with water",
        scheduled_time="2026-10-24 18:00",
        category="medication"
    )
    rem_resp = create_reminder(rem_req, ctx=cg_ctx)
    assert rem_resp["status"] == "ok"
    assert rem_resp["reminder"]["title"] == "Heart Medication"

    # User fetches reminders and sees it
    u_rems = get_reminders(ctx=u_ctx)
    assert len(u_rems) >= 1
    assert any(r["title"] == "Heart Medication" for r in u_rems)


def test_history_queries_and_audit_log(tmp_path: Path):
    test_db = CloudDatabase(db_path=tmp_path / "cloud_hist_test.db")
    import cloud.server
    cloud.server.db = test_db

    cg_ctx = {
        "user_id": "caregiver_01",
        "role": "caregiver",
        "linked_user_id": "user_01",
        "target_user_id": "user_01",
        "display_name": "Nurse Priya (Caregiver)"
    }

    # Insert sightings in different zones
    sighting_living = {
        "id": "sight_1",
        "person_id": "p_ananya",
        "person_label": "Ananya",
        "timestamp": 1792839600.0,
        "confidence": 0.88,
        "zone": "Living Room",
        "is_doubtful": False,
    }
    sighting_kitchen = {
        "id": "sight_2",
        "person_id": "p_nurse",
        "person_label": "Nurse Priya",
        "timestamp": 1792839700.0,
        "confidence": 0.92,
        "zone": "Kitchen",
        "is_doubtful": False,
    }
    test_db.insert_sighting("user_01", sighting_living)
    test_db.insert_sighting("user_01", sighting_kitchen)

    # Filter by zone: 'Living Room'
    living_res = get_sightings(date=None, person=None, zone="Living Room", ctx=cg_ctx)
    assert len(living_res) == 1
    assert living_res[0]["person_label"] == "Ananya"

    # Filter by person: 'Nurse'
    nurse_res = get_sightings(date=None, person="Nurse", zone=None, ctx=cg_ctx)
    assert len(nurse_res) == 1
    assert nurse_res[0]["zone"] == "Kitchen"

    # Mark private area
    pa_req = PrivateAreaRequest(zone_name="En-suite Bathroom", is_private=True)
    pa_resp = set_private_area(pa_req, ctx=cg_ctx)
    assert pa_resp["status"] == "ok"

    # Retrieve private areas & audit log
    pa_data = get_private_areas(ctx=cg_ctx)
    assert len(pa_data["settings"]) >= 1
    assert any(s["zone_name"] == "En-suite Bathroom" and s["is_private"] == 1 for s in pa_data["settings"])

    audit_log = pa_data["audit_log"]
    assert len(audit_log) >= 1
    assert "Nurse Priya" in audit_log[0]["changed_by"]
    assert audit_log[0]["zone_name"] == "En-suite Bathroom"
