"""
Unit tests for SecureStorage: encryption verification and time-limited data retention policies.
"""

import time
from pathlib import Path
from device.models import Person, PersonStatus, ConversationSummary, Note, EmergencyAlert
from device.storage import SecureStorage


def test_encryption_at_rest(tmp_path: Path):
    db_file = tmp_path / "enc_test.db"
    storage = SecureStorage(db_path=db_file, encryption_key="my_super_secret_key_123")

    p = Person(
        label="Dr. Smith",
        relationship="Doctor",
        status=PersonStatus.FAMILIAR,
        embedding=[0.1, 0.2, 0.3],
        notes="Allergic to penicillin; check blood pressure."
    )
    storage.save_person(p)

    # Read raw SQLite content to confirm ciphertext is NOT stored as plaintext
    import sqlite3
    raw_conn = sqlite3.connect(str(db_file))
    cursor = raw_conn.cursor()
    cursor.execute("SELECT embedding_cipher, notes_cipher FROM people WHERE id = ?", (p.id,))
    row = cursor.fetchone()
    raw_emb = row[0]
    raw_notes = row[1]

    assert "penicillin" not in raw_notes
    assert "[0.1, 0.2, 0.3]" not in raw_emb

    # Read back via SecureStorage -> decrypted successfully
    retrieved = storage.get_person(p.id)
    assert retrieved is not None
    assert retrieved.notes == "Allergic to penicillin; check blood pressure."
    assert retrieved.embedding == [0.1, 0.2, 0.3]


def test_time_limited_retention_rules(tmp_path: Path):
    db_file = tmp_path / "retention_test.db"
    storage = SecureStorage(db_path=db_file)
    now = time.time()
    day = 86400

    # 1. One-time stranger seen 35 days ago (should be purged)
    old_stranger = Person(
        label="Unknown #99",
        status=PersonStatus.STRANGER,
        first_seen=now - (35 * day),
        last_seen=now - (35 * day),
    )
    storage.save_person(old_stranger)

    # 2. Familiar person seen 40 days ago (must NOT be purged)
    old_familiar = Person(
        label="Granddaughter Ananya",
        status=PersonStatus.FAMILIAR,
        first_seen=now - (40 * day),
        last_seen=now - (40 * day),
    )
    storage.save_person(old_familiar)

    # 3. Old conversation summary (70 days ago, should be purged)
    old_summary = ConversationSummary(
        summary="Old casual talk",
        timestamp=now - (70 * day),
    )
    storage.save_summary(old_summary)

    # 4. Recent conversation summary (10 days ago, must NOT be purged)
    recent_summary = ConversationSummary(
        summary="Important doctor instructions",
        timestamp=now - (10 * day),
    )
    storage.save_summary(recent_summary)

    # 5. Old note (80 days ago, should be purged)
    old_note = Note(
        content="Old reminder note",
        created_at=now - (80 * day),
    )
    storage.save_note(old_note)

    # 6. Critical Emergency Alert from 100 days ago (MUST NEVER BE PURGED!)
    emergency = EmergencyAlert(
        timestamp=now - (100 * day),
        pulse_bpm=145.0,
        motion_status="sudden_fall_impact",
        location_zone="Bathroom",
        severity="CRITICAL",
        trigger_reason="Severe fall with rapid pulse spike",
    )
    storage.save_alert(emergency)

    # Run Retention Cleanup
    results = storage.run_retention_cleanup(
        current_time=now,
        stranger_days=30,
        notes_days=60
    )

    assert results["deleted_strangers"] == 1
    assert results["deleted_summaries"] == 1
    assert results["deleted_notes"] == 1

    # Verify Database state
    assert storage.get_person(old_stranger.id) is None
    assert storage.get_person(old_familiar.id) is not None

    all_summaries = storage.get_summaries()
    assert len(all_summaries) == 1
    assert all_summaries[0].id == recent_summary.id

    # Emergency alerts are intact
    all_alerts = storage.get_alerts()
    assert len(all_alerts) == 1
    assert all_alerts[0].id == emergency.id
