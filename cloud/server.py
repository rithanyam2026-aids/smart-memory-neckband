"""
FastAPI Cloud Backend Server for Smart Memory Neckband.
Serves HTTPS REST APIs, serves dashboard static web app, and handles bidirectional sync.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from cloud.database import CloudDatabase
from cloud.auth import generate_token, get_current_user_context
from cloud.mqtt_handler import MQTTHandler
from device.config import config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
BLUEPRINT_PATH = PROJECT_ROOT / "data" / "house_grid.sample.json"

db = CloudDatabase()
mqtt_handler = MQTTHandler(db)

app = FastAPI(
    title="Smart Memory Neckband Cloud API",
    description="Backend service providing authentication, sync, and dashboard serving",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request/Response Models ---
class LoginRequest(BaseModel):
    role: str  # 'user' or 'caregiver'
    pin: str


class PersonUpdateRequest(BaseModel):
    label: str
    relationship: Optional[str] = None


class NoteCreateRequest(BaseModel):
    content: str
    reminder_id: Optional[str] = None
    person_id: Optional[str] = None
    date: Optional[str] = None


class ReminderCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    scheduled_time: str
    category: str = "medication"


class PrivateAreaRequest(BaseModel):
    zone_name: Optional[str] = None
    cell_row: Optional[int] = None
    cell_col: Optional[int] = None
    is_private: bool


class SyncUpstreamRequest(BaseModel):
    people: List[Dict[str, Any]] = []
    sightings: List[Dict[str, Any]] = []
    summaries: List[Dict[str, Any]] = []
    notes: List[Dict[str, Any]] = []
    alerts: List[Dict[str, Any]] = []
    privacy_logs: List[Dict[str, Any]] = []
    device_status: Optional[Dict[str, Any]] = None


# --- Authentication Endpoint ---
@app.post("/api/auth/login")
def login(req: LoginRequest):
    if req.role == "caregiver":
        if req.pin == "1234":
            token = generate_token({
                "user_id": "caregiver_01",
                "role": "caregiver",
                "linked_user_id": "user_01",
                "display_name": "Nurse Priya (Caregiver)"
            })
            return {"token": token, "role": "caregiver", "display_name": "Nurse Priya", "target_user_id": "user_01"}
        raise HTTPException(status_code=401, detail="Invalid Caregiver PIN")

    elif req.role == "user":
        if req.pin == "0000":
            token = generate_token({
                "user_id": "user_01",
                "role": "user",
                "linked_user_id": None,
                "display_name": "Senior Resident"
            })
            return {"token": token, "role": "user", "display_name": "Senior Resident", "target_user_id": "user_01"}
        raise HTTPException(status_code=401, detail="Invalid User PIN")

    raise HTTPException(status_code=400, detail="Invalid role specified")


# --- Device Status & Telemetry ---
@app.get("/api/status")
def get_status(ctx: Dict[str, Any] = Depends(get_current_user_context)):
    return db.get_device_status(ctx["target_user_id"])


@app.post("/api/status")
def update_status(status_data: Dict[str, Any], ctx: Dict[str, Any] = Depends(get_current_user_context)):
    db.update_device_status(ctx["target_user_id"], status_data)
    return {"status": "ok"}


# --- People Management ---
@app.get("/api/people")
def get_people(ctx: Dict[str, Any] = Depends(get_current_user_context)):
    return db.get_people(ctx["target_user_id"])


@app.put("/api/people/{person_id}")
def update_person(person_id: str, req: PersonUpdateRequest, ctx: Dict[str, Any] = Depends(get_current_user_context)):
    db.update_person_label_and_relationship(ctx["target_user_id"], person_id, req.label, req.relationship)
    return {"status": "ok", "message": "Person label and relationship updated"}


# --- History Queries: Sightings & Summaries ---
@app.get("/api/sightings")
def get_sightings(
    date: Optional[str] = Query(None, description="Filter by YYYY-MM-DD"),
    person: Optional[str] = Query(None, description="Filter by person name/id"),
    zone: Optional[str] = Query(None, description="Filter by room zone"),
    ctx: Dict[str, Any] = Depends(get_current_user_context)
):
    return db.query_sightings(ctx["target_user_id"], date_str=date, person_query=person, zone=zone)


@app.get("/api/summaries")
def get_summaries(
    date: Optional[str] = Query(None, description="Filter by YYYY-MM-DD"),
    person: Optional[str] = Query(None, description="Filter by person name"),
    ctx: Dict[str, Any] = Depends(get_current_user_context)
):
    return db.query_summaries(ctx["target_user_id"], date_str=date, person_query=person)


# --- Notes CRUD ---
@app.get("/api/notes")
def get_notes(date: Optional[str] = None, ctx: Dict[str, Any] = Depends(get_current_user_context)):
    return db.get_notes(ctx["target_user_id"], date_str=date)


@app.post("/api/notes")
def create_note(req: NoteCreateRequest, ctx: Dict[str, Any] = Depends(get_current_user_context)):
    import uuid, datetime
    note_id = f"note_{uuid.uuid4().hex[:8]}"
    author_role = ctx["role"]
    author_name = ctx["display_name"]
    note_date = req.date or datetime.date.today().isoformat()
    note_data = {
        "id": note_id,
        "reminder_id": req.reminder_id,
        "person_id": req.person_id,
        "date": note_date,
        "content": req.content,
        "author_role": author_role,
        "author_name": author_name,
    }
    db.insert_note(ctx["target_user_id"], note_data)
    return {"status": "ok", "note": note_data}


# --- Reminders CRUD ---
@app.get("/api/reminders")
def get_reminders(ctx: Dict[str, Any] = Depends(get_current_user_context)):
    return db.get_reminders(ctx["target_user_id"])


@app.post("/api/reminders")
def create_reminder(req: ReminderCreateRequest, ctx: Dict[str, Any] = Depends(get_current_user_context)):
    import uuid
    rem_id = f"rem_{uuid.uuid4().hex[:8]}"
    rem_data = {
        "id": rem_id,
        "title": req.title,
        "description": req.description,
        "scheduled_time": req.scheduled_time,
        "category": req.category,
        "is_active": True,
        "spoken": False,
        "created_by": ctx["display_name"]
    }
    db.upsert_reminder(ctx["target_user_id"], rem_data)
    return {"status": "ok", "reminder": rem_data}


@app.put("/api/reminders/{reminder_id}")
def edit_reminder(reminder_id: str, req: ReminderCreateRequest, ctx: Dict[str, Any] = Depends(get_current_user_context)):
    rem_data = {
        "id": reminder_id,
        "title": req.title,
        "description": req.description,
        "scheduled_time": req.scheduled_time,
        "category": req.category,
        "is_active": True,
        "spoken": False,
        "created_by": ctx["display_name"]
    }
    db.upsert_reminder(ctx["target_user_id"], rem_data)
    return {"status": "ok", "reminder": rem_data}


@app.delete("/api/reminders/{reminder_id}")
def delete_reminder(reminder_id: str, ctx: Dict[str, Any] = Depends(get_current_user_context)):
    db.delete_reminder(ctx["target_user_id"], reminder_id)
    return {"status": "ok", "message": "Reminder deleted"}


# --- Emergency Alerts ---
@app.get("/api/alerts")
def get_alerts(ctx: Dict[str, Any] = Depends(get_current_user_context)):
    return db.get_alerts(ctx["target_user_id"])


@app.post("/api/alerts")
def report_alert(alert_data: Dict[str, Any], ctx: Dict[str, Any] = Depends(get_current_user_context)):
    db.insert_alert(ctx["target_user_id"], alert_data)
    return {"status": "ok", "message": "Emergency alert recorded and broadcast"}


# --- House Blueprint & Private Areas ---
@app.get("/api/grid/blueprint")
def get_blueprint():
    if not BLUEPRINT_PATH.exists():
        raise HTTPException(status_code=404, detail="Blueprint file not found")
    with open(BLUEPRINT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/private-areas")
def get_private_areas(ctx: Dict[str, Any] = Depends(get_current_user_context)):
    return {
        "settings": db.get_private_area_settings(ctx["target_user_id"]),
        "audit_log": db.get_private_area_audit_log(ctx["target_user_id"])
    }


@app.post("/api/private-areas")
def set_private_area(req: PrivateAreaRequest, ctx: Dict[str, Any] = Depends(get_current_user_context)):
    db.set_private_area(
        user_id=ctx["target_user_id"],
        is_private=req.is_private,
        changed_by=f"{ctx['display_name']} ({ctx['role']})",
        zone_name=req.zone_name,
        cell_row=req.cell_row,
        cell_col=req.cell_col
    )
    return {"status": "ok", "message": "Private area setting saved and logged in audit record"}


@app.get("/api/privacy-logs")
def get_privacy_logs(ctx: Dict[str, Any] = Depends(get_current_user_context)):
    return db.get_privacy_logs(ctx["target_user_id"])


# --- Bidirectional Sync Protocol ---
@app.post("/api/sync/upstream")
def sync_upstream(req: SyncUpstreamRequest, ctx: Dict[str, Any] = Depends(get_current_user_context)):
    target_id = ctx["target_user_id"]
    for p in req.people:
        db.upsert_person(target_id, p)
    for s in req.sightings:
        db.insert_sighting(target_id, s)
    for sm in req.summaries:
        db.insert_summary(target_id, sm)
    for n in req.notes:
        db.insert_note(target_id, n)
    for a in req.alerts:
        db.insert_alert(target_id, a)
    for l in req.privacy_logs:
        db.insert_privacy_log(target_id, l)
    if req.device_status:
        db.update_device_status(target_id, req.device_status)

    return {"status": "ok", "synced_items": len(req.people) + len(req.sightings) + len(req.summaries)}


@app.get("/api/sync/downstream")
def sync_downstream(ctx: Dict[str, Any] = Depends(get_current_user_context)):
    target_id = ctx["target_user_id"]
    return {
        "people": db.get_people(target_id),
        "reminders": db.get_reminders(target_id),
        "notes": db.get_notes(target_id),
        "private_areas": db.get_private_area_settings(target_id),
    }


# --- Dashboard Static Web App Serving ---
if DASHBOARD_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")

    @app.get("/")
    def serve_root_dashboard():
        index_file = DASHBOARD_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"message": "Smart Memory Neckband Cloud API active. Dashboard index pending."}
