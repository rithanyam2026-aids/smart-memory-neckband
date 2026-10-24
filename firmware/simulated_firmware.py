"""
Simulated ESP32-S3 Firmware Runner.
Mirrors the exact C++ firmware logic for desktop testing:
- Hardware power gate simulation (cuts camera & mic power in PRIVATE)
- Loads house grid JSON blueprint and tracks inside/outside through exit/entrance cells
- Dynamic private areas stored in simulated flash
- Combined pulse + motion emergency alert rule (pulse alone does NOT alert)
- Link protocol client communicating with Python AI service
- Fail-safe: Link loss immediately forces state to PRIVATE or SLEEP (never ACTIVE)
"""

from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Set

from ai.protocol import MsgType, LinkProtocolPacket, LinkAuthenticator


class SimulatedFirmware:
    def __init__(
        self,
        blueprint_data: Dict[str, Any],
        link_psk: str = "smart_memory_neckband_psk_shared_key_32b_fixed",
        device_id: str = "neckband-01"
    ):
        self.device_id = device_id
        self.authenticator = LinkAuthenticator(psk=link_psk)

        # Grid and Blueprints
        self.rows = blueprint_data.get("dimensions", {}).get("rows", 8)
        self.cols = blueprint_data.get("dimensions", {}).get("columns", 10)
        self.entrances = {(e["row"], e["col"]) for e in blueprint_data.get("entrances", [])}
        self.exits = {(e["row"], e["col"]) for e in blueprint_data.get("exits", [])}

        self.cell_to_zone: Dict[Tuple[int, int], str] = {}
        for z in blueprint_data.get("named_zones", []):
            for c in z.get("cells", []):
                self.cell_to_zone[(c["row"], c["col"])] = z["name"]

        # Simulated Flash Storage (Private area settings)
        self.flash_private_zones: Set[str] = set()
        self.flash_private_cells: Set[Tuple[int, int]] = set()

        # State Machine
        self.privacy_state = "SLEEP"  # "PRIVATE", "SLEEP", "ACTIVE"
        self.location_state = "INSIDE"  # "INSIDE", "OUTSIDE"
        self.current_cell: Optional[Tuple[int, int]] = (7, 4)  # Default entrance door
        self.current_zone: str = self.get_zone(7, 4)

        # Hardware Power Gates (True = Powered ON, False = Cut off)
        self.camera_power_gate = False
        self.mic_power_gate = False
        self.status_led = "SLEEP"

        # Link status
        self.is_link_connected = True
        self.last_heartbeat_ack = time.time()
        self.last_person_seen = 0.0
        self.active_silence_timeout = 15.0

        self.update_hardware_power_gates()

    def get_zone(self, r: int, c: int) -> str:
        if not (0 <= r < self.rows and 0 <= c < self.cols):
            return "Outside"
        return self.cell_to_zone.get((r, c), "General Hallway")

    def is_area_private(self, r: Optional[int], c: Optional[int]) -> bool:
        if r is not None and c is not None:
            if (r, c) in self.flash_private_cells:
                return True
            zone = self.get_zone(r, c)
            if zone in self.flash_private_zones:
                return True
        return False

    def update_hardware_power_gates(self):
        """Hardware power gate: cuts off camera and mic power in PRIVATE and SLEEP."""
        if self.privacy_state == "ACTIVE":
            self.camera_power_gate = True
            self.mic_power_gate = True
            self.status_led = "ACTIVE_GREEN"
        else:
            self.camera_power_gate = False
            self.mic_power_gate = False
            self.status_led = "PRIVATE_RED" if self.privacy_state == "PRIVATE" else "SLEEP_BLUE"

    def apply_link_loss_failsafe(self):
        """CRITICAL FAILSAFE: If link to AI service is lost, never remain in ACTIVE!"""
        self.is_link_connected = False
        if self.privacy_state == "ACTIVE":
            self.transition_to("SLEEP", "Link loss detected. Failsafe transition to SLEEP.")

    def set_link_restored(self):
        self.is_link_connected = True
        self.last_heartbeat_ack = time.time()

    def transition_to(self, new_state: str, reason: str):
        if self.privacy_state == new_state:
            return
        self.privacy_state = new_state
        self.update_hardware_power_gates()

    def update_position(self, r: Optional[int], c: Optional[int]):
        prev_cell = self.current_cell
        prev_loc = self.location_state

        if r is not None and c is not None and (0 <= r < self.rows and 0 <= c < self.cols):
            self.location_state = "INSIDE"
            self.current_cell = (r, c)
            self.current_zone = self.get_zone(r, c)
        else:
            self.location_state = "OUTSIDE"
            self.current_cell = None
            self.current_zone = "Outside"

        # Inside house privacy evaluation
        if self.location_state == "INSIDE":
            if self.is_area_private(self.current_cell[0], self.current_cell[1]):
                if self.privacy_state != "PRIVATE":
                    self.transition_to("PRIVATE", f"Entered private room/cell ({self.current_zone})")
            else:
                if self.privacy_state == "PRIVATE":
                    # Leaving private area -> return to SLEEP (never straight to ACTIVE)
                    self.transition_to("SLEEP", f"Exited private room to normal zone ({self.current_zone}). Set to SLEEP.")
        else:
            # Outside house
            if prev_loc == "INSIDE":
                self.transition_to("SLEEP", "Exited house boundary. Default state SLEEP.")

    def on_outside_scene_result(self, classification: str):
        """Process result from AI service scene check."""
        if not self.is_link_connected or classification in ("PRIVATE", "UNDECIDED"):
            # Toilet-like venue or undecided or link down -> go to or stay in PRIVATE
            if self.privacy_state != "PRIVATE":
                self.transition_to("PRIVATE", "Outside check detected private venue or undecided/link-down.")
        elif classification == "NOT_PRIVATE":
            if self.privacy_state == "PRIVATE":
                self.transition_to("SLEEP", "Outside check confirmed non-private venue. Return to SLEEP.")

    def on_person_detected(self):
        # Can only wake to ACTIVE if link is alive and not in PRIVATE
        if self.privacy_state == "SLEEP" and self.is_link_connected:
            self.last_person_seen = time.time()
            self.transition_to("ACTIVE", "Face or speech detected while in SLEEP.")
        elif self.privacy_state == "ACTIVE":
            self.last_person_seen = time.time()

    def on_person_left_or_silence(self):
        if self.privacy_state == "ACTIVE":
            self.transition_to("SLEEP", "Person departed or silence duration exceeded.")

    def evaluate_vitals_emergency(self, pulse_bpm: float, motion_status: str) -> Optional[Dict[str, Any]]:
        """
        Evaluate pulse and motion together.
        Never alert on pulse alone or motion alone.
        """
        is_pulse_abnormal = (pulse_bpm >= 130.0 or pulse_bpm <= 40.0)
        is_motion_critical = motion_status in ("sudden_fall_impact", "immobility", "severe_impact")

        if is_pulse_abnormal and is_motion_critical:
            return {
                "id": f"alert_esp_{int(time.time()*1000)}",
                "timestamp": time.time(),
                "pulse_bpm": pulse_bpm,
                "motion_status": motion_status,
                "zone": self.current_zone,
                "cell": self.current_cell,
                "trigger_reason": f"Abnormal pulse ({pulse_bpm} BPM) combined with critical motion ({motion_status})",
                "severity": "CRITICAL"
            }
        return None

    def apply_downstream_sync_settings(self, settings: Dict[str, Any]):
        """Save settings into simulated LittleFS flash."""
        self.flash_private_zones = set(settings.get("private_zones", []))
        self.flash_private_cells = {tuple(c) for c in settings.get("private_cells", [])}
