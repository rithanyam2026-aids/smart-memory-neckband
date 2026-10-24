"""
Unit and Integration Tests for ESP32 Firmware Logic, Link Protocol, and Fail-safes:
- Link protocol packet framing and CRC32 verification
- Mutual challenge-response authentication
- Link loss causing immediate transition to SLEEP/PRIVATE and hardware power gate cut-off
- Outside scene check: toilet-like private place -> PRIVATE
- Outside scene check: non-private -> SLEEP
- Outside scene check: undecided check -> PRIVATE (fail-safe)
- Inside house: private room -> PRIVATE, leaving private -> SLEEP
- Pulse and motion combined emergency alert rule
"""

import json
from pathlib import Path
from ai.protocol import MsgType, LinkProtocolPacket, LinkAuthenticator
from firmware.simulated_firmware import SimulatedFirmware


def load_sample_blueprint() -> dict:
    path = Path(__file__).resolve().parent.parent / "data" / "house_grid.sample.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_link_protocol_packet_encoding_and_crc():
    meta = {"zone": "Living Room", "battery": 95}
    body = b"JPEG_IMAGE_TEST_FRAME_BYTES_12345"
    packet = LinkProtocolPacket.encode_packet(
        msg_type=MsgType.FRAME_STREAM,
        metadata=meta,
        binary_payload=body,
        seq_no=42
    )
    assert len(packet) > LinkProtocolPacket.HEADER_SIZE

    mtype, decoded_meta, decoded_body, seq = LinkProtocolPacket.decode_packet(packet)
    assert mtype == MsgType.FRAME_STREAM
    assert decoded_meta["zone"] == "Living Room"
    assert decoded_meta["battery"] == 95
    assert decoded_body == body
    assert seq == 42


def test_mutual_pairing_challenge_response():
    auth = LinkAuthenticator(psk="my_secret_psk_key_123")
    nonce = "random_nonce_98765"
    challenge = auth.generate_challenge(nonce)

    assert auth.verify_challenge(nonce, challenge) is True
    assert auth.verify_challenge(nonce, "tampered_challenge") is False


def test_link_loss_failsafe_cuts_power_gates():
    bp = load_sample_blueprint()
    firmware = SimulatedFirmware(blueprint_data=bp)

    # Put firmware into ACTIVE state (person present)
    firmware.on_person_detected()
    assert firmware.privacy_state == "ACTIVE"
    assert firmware.camera_power_gate is True
    assert firmware.mic_power_gate is True

    # SIMULATE LINK DROP: AI service stops pinging or hotspot disconnects
    firmware.apply_link_loss_failsafe()

    # STRICT FAILSAFE: Must not remain in ACTIVE!
    assert firmware.privacy_state in ("SLEEP", "PRIVATE")
    # Hardware power gates must be physically cut off
    assert firmware.camera_power_gate is False
    assert firmware.mic_power_gate is False

    # While link is down, person detection CANNOT wake camera to ACTIVE
    firmware.on_person_detected()
    assert firmware.privacy_state != "ACTIVE"


def test_outside_toilet_check_transitions_to_private():
    bp = load_sample_blueprint()
    firmware = SimulatedFirmware(blueprint_data=bp)

    # Step outside house boundary (row 8, col 4)
    firmware.update_position(8, 4)
    assert firmware.location_state == "OUTSIDE"
    assert firmware.privacy_state == "SLEEP"

    # 1. AI service scene check returns "PRIVATE" (toilet/restroom detected)
    firmware.on_outside_scene_result("PRIVATE")
    assert firmware.privacy_state == "PRIVATE"
    assert firmware.camera_power_gate is False
    assert firmware.mic_power_gate is False

    # 2. Outside check still private -> stays in PRIVATE
    firmware.on_outside_scene_result("PRIVATE")
    assert firmware.privacy_state == "PRIVATE"

    # 3. User steps out to sidewalk / park -> AI service returns "NOT_PRIVATE"
    firmware.on_outside_scene_result("NOT_PRIVATE")
    assert firmware.privacy_state == "SLEEP"

    # 4. AI service cannot decide (returns "UNDECIDED") -> treats as PRIVATE (fail-safe)
    firmware.on_outside_scene_result("UNDECIDED")
    assert firmware.privacy_state == "PRIVATE"


def test_inside_house_private_room_and_cell_overrides():
    bp = load_sample_blueprint()
    firmware = SimulatedFirmware(blueprint_data=bp)

    # Dashboard syncs private area settings into firmware flash
    firmware.apply_downstream_sync_settings({
        "private_zones": ["Master Bedroom"],
        "private_cells": [[1, 2]]  # Medicine cabinet in kitchen
    })

    # Start in Hallway
    firmware.update_position(5, 4)
    assert firmware.privacy_state == "SLEEP"

    # Enter Master Bedroom (row 2, col 6) -> goes to PRIVATE immediately
    firmware.update_position(2, 6)
    assert firmware.privacy_state == "PRIVATE"
    assert firmware.camera_power_gate is False

    # Leave Master Bedroom back into Hallway -> goes back to SLEEP (never straight to ACTIVE)
    firmware.update_position(5, 4)
    assert firmware.privacy_state == "SLEEP"
    assert firmware.camera_power_gate is False

    # Walk to Kitchen private cell (1, 2) -> PRIVATE
    firmware.update_position(1, 2)
    assert firmware.privacy_state == "PRIVATE"

    # Step to adjacent Kitchen cell (1, 3) which is normal -> returns to SLEEP
    firmware.update_position(1, 3)
    assert firmware.privacy_state == "SLEEP"


def test_firmware_pulse_and_motion_alert_rule():
    bp = load_sample_blueprint()
    firmware = SimulatedFirmware(blueprint_data=bp)

    # 1. High pulse alone (145 BPM) with normal motion -> No alert
    assert firmware.evaluate_vitals_emergency(pulse_bpm=145.0, motion_status="normal") is None

    # 2. Motion fall impact alone with normal pulse (72 BPM) -> No alert
    assert firmware.evaluate_vitals_emergency(pulse_bpm=72.0, motion_status="sudden_fall_impact") is None

    # 3. Pulse collapse (< 40 BPM) combined with immobility -> CRITICAL Emergency Alert
    alert = firmware.evaluate_vitals_emergency(pulse_bpm=35.0, motion_status="immobility")
    assert alert is not None
    assert alert["severity"] == "CRITICAL"
    assert "Abnormal pulse (35.0 BPM) combined with critical motion" in alert["trigger_reason"]
