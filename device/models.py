"""
Data models for the Smart Memory Neckband system.
Supports serialization, validation, and type-safe access across device, cloud, and mobile.
"""

from __future__ import annotations
import uuid
import datetime
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field


class PrivacyState(str, Enum):
    PRIVATE = "PRIVATE"
    SLEEP = "SLEEP"
    ACTIVE = "ACTIVE"


class LocationState(str, Enum):
    INSIDE = "INSIDE"
    OUTSIDE = "OUTSIDE"
    UNKNOWN = "UNKNOWN"


class PersonStatus(str, Enum):
    STRANGER = "stranger"
    FAMILIAR = "familiar"
    KNOWN = "known"


class Person(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    label: str  # e.g., "Unknown #1" or "Granddaughter Ananya"
    relationship: Optional[str] = None
    status: PersonStatus = PersonStatus.STRANGER
    visit_count: int = 1
    embedding: List[float] = Field(default_factory=list)
    embedding_sample_count: int = 1
    first_seen: float = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).timestamp())
    last_seen: float = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).timestamp())
    notes: Optional[str] = None
    sync_status: str = "synced"  # 'pending', 'synced'

    def is_expired(self, current_time: float, stranger_retention_days: int = 30) -> bool:
        """
        Strangers are deleted if not seen within stranger_retention_days.
        Familiar/known contacts retain and clock resets at each encounter.
        """
        if self.status in (PersonStatus.FAMILIAR, PersonStatus.KNOWN):
            return False
        retention_secs = stranger_retention_days * 86400
        return (current_time - self.last_seen) > retention_secs


class Sighting(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    person_id: str
    person_label: str
    timestamp: float = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).timestamp())
    confidence: float = 0.0
    zone: Optional[str] = None
    grid_cell: Optional[Tuple[int, int]] = None
    is_doubtful: bool = False  # True when match confidence is in "I'm not sure" band
    doubtful_message: Optional[str] = None
    sync_status: str = "pending"


class ConversationSummary(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    person_id: Optional[str] = None
    person_label: Optional[str] = None
    timestamp: float = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).timestamp())
    transcript: Optional[str] = None
    summary: str
    importance_score: float = 0.0
    key_entities: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    sync_status: str = "pending"

    def is_expired(self, current_time: float, notes_retention_days: int = 60) -> bool:
        retention_secs = notes_retention_days * 86400
        return (current_time - self.timestamp) > retention_secs


class Note(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    reminder_id: Optional[str] = None
    person_id: Optional[str] = None
    date: str = Field(default_factory=lambda: datetime.date.today().isoformat())
    content: str
    author_role: str = "user"  # 'user' or 'caregiver'
    author_name: str = "User"
    created_at: float = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).timestamp())
    sync_status: str = "pending"


class Reminder(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: Optional[str] = None
    scheduled_time: str  # ISO string or HH:MM / YYYY-MM-DD HH:MM
    category: str = "medication"  # 'medication', 'appointment', 'schedule', 'daily_summary'
    is_active: bool = True
    spoken: bool = False
    created_by: str = "caregiver"
    created_at: float = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).timestamp())
    sync_status: str = "synced"


class EmergencyAlert(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).timestamp())
    pulse_bpm: float
    motion_status: str  # 'sudden_fall_impact', 'immobility', 'normal'
    location_zone: Optional[str] = None
    grid_cell: Optional[Tuple[int, int]] = None
    gps_coords: Optional[Dict[str, float]] = None
    severity: str = "CRITICAL"
    resolved: bool = False
    trigger_reason: str
    sync_status: str = "pending"


class PrivateAreaSetting(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    zone_name: Optional[str] = None
    cell_row: Optional[int] = None
    cell_col: Optional[int] = None
    is_private: bool = True
    set_by: str = "caregiver"  # 'user' or 'caregiver'
    updated_at: float = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).timestamp())


class PrivacyLogEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).timestamp())
    state: PrivacyState
    is_inside: bool
    zone: Optional[str] = None
    cell_row: Optional[int] = None
    cell_col: Optional[int] = None
    reason: str
    sync_status: str = "pending"


class DeviceTelemetry(BaseModel):
    device_id: str = "neckband-01"
    battery_pct: float = 95.0
    privacy_state: PrivacyState = PrivacyState.SLEEP
    is_inside: bool = True
    current_zone: Optional[str] = "Living Room"
    grid_cell: Optional[Tuple[int, int]] = (3, 2)
    timestamp: float = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).timestamp())
    camera_active: bool = False
    mic_active: bool = False
    sensors_active: bool = True
