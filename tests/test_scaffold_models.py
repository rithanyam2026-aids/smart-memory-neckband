"""
Tests for Step 1: Scaffold, Data Models, and Grid Blueprint Schema
"""
import json
from pathlib import Path
from device.models import (
    Person, PersonStatus, Sighting, ConversationSummary, Note, Reminder,
    EmergencyAlert, PrivateAreaSetting, PrivacyLogEntry, PrivacyState, LocationState
)
from device.config import config


def test_models_instantiation():
    person = Person(label="Unknown #1", status=PersonStatus.STRANGER, visit_count=1)
    assert person.label == "Unknown #1"
    assert person.status == PersonStatus.STRANGER
    assert person.visit_count == 1
    assert person.is_expired(person.last_seen + 31 * 86400, stranger_retention_days=30) is True
    assert person.is_expired(person.last_seen + 10 * 86400, stranger_retention_days=30) is False

    # Familiar person never expires under stranger retention rules
    person.status = PersonStatus.FAMILIAR
    assert person.is_expired(person.last_seen + 100 * 86400, stranger_retention_days=30) is False


def test_conversation_summary_retention():
    summary = ConversationSummary(
        summary="Spoke about morning medicine and college visit",
        importance_score=0.85
    )
    assert summary.is_expired(summary.timestamp + 61 * 86400, notes_retention_days=60) is True
    assert summary.is_expired(summary.timestamp + 15 * 86400, notes_retention_days=60) is False


def test_blueprint_json_integrity():
    blueprint_path = Path(__file__).resolve().parent.parent / "data" / "house_grid.sample.json"
    assert blueprint_path.exists(), "Blueprint file must exist"
    with open(blueprint_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "dimensions" in data
    assert data["dimensions"]["rows"] > 0
    assert data["dimensions"]["columns"] > 0
    assert len(data["entrances"]) >= 1
    assert len(data["exits"]) >= 1
    assert len(data["named_zones"]) >= 1
