"""
Link Protocol Server for Python AI Service.
Handles pairing, challenge-response auth, heartbeat monitoring,
and message dispatching from/to the ESP32 Neckband.
"""

from __future__ import annotations
import time
import logging
from typing import Optional, Dict, Any, Callable

from ai.config import config
from ai.protocol import MsgType, LinkProtocolPacket, LinkAuthenticator
from ai.face_recognition import FaceRecognitionEngine
from ai.speech_llm import ConversationPipeline
from ai.scene_classifier import SceneClassifier, AudioVisualSceneClassifier
from ai.storage import SecureStorage
from ai.models import EmergencyAlert, PrivacyLogEntry, PrivacyState

logger = logging.getLogger("AILinkServer")


class AILinkServer:
    def __init__(
        self,
        storage: SecureStorage,
        face_engine: Optional[FaceRecognitionEngine] = None,
        conversation_pipeline: Optional[ConversationPipeline] = None,
        scene_classifier: Optional[SceneClassifier] = None,
        on_speaker_dispatch: Optional[Callable[[str], None]] = None,
    ):
        self.storage = storage
        self.face_engine = face_engine or FaceRecognitionEngine(storage=self.storage)
        self.conversation_pipeline = conversation_pipeline or ConversationPipeline(storage=self.storage)
        self.scene_classifier = scene_classifier or AudioVisualSceneClassifier()
        self.authenticator = LinkAuthenticator(psk=config.LINK_PRESHARED_KEY)
        self.on_speaker_dispatch = on_speaker_dispatch

        # Connection status tracking
        self.is_connected = False
        self.session_id: Optional[str] = None
        self.last_heartbeat_time: float = 0.0
        self.heartbeat_timeout = config.LINK_HEARTBEAT_TIMEOUT_SEC

    def handle_incoming_packet(self, packet_bytes: bytes) -> Optional[bytes]:
        """
        Process a raw link packet from the ESP32 neckband.
        Returns a response packet bytes if required.
        """
        try:
            msg_type, metadata, binary_body, seq = LinkProtocolPacket.decode_packet(packet_bytes)
        except Exception as e:
            logger.error(f"Packet decode error: {e}")
            return None

        # 1. Pairing Handshake Initiation
        if msg_type == MsgType.HANDSHAKE_HELLO:
            device_id = metadata.get("device_id")
            nonce_c = metadata.get("nonce_c", "")
            if device_id != config.DEVICE_ID:
                logger.warning(f"Unauthorized device ID: {device_id}")
                return None

            hmac_c = self.authenticator.generate_challenge(nonce_c)
            self.session_id = f"sess_{int(time.time()*1000)}"
            resp_meta = {
                "session_id": self.session_id,
                "nonce_s": f"nonce_s_{int(time.time()*1000)}",
                "hmac_c": hmac_c,
            }
            return LinkProtocolPacket.encode_packet(MsgType.HANDSHAKE_AUTH, resp_meta)

        # 2. Handshake Verification Completion
        elif msg_type == MsgType.HANDSHAKE_AUTH:
            nonce_s = metadata.get("nonce_s", "")
            hmac_s = metadata.get("hmac_s", "")
            if self.authenticator.verify_challenge(nonce_s, hmac_s):
                self.is_connected = True
                self.last_heartbeat_time = time.time()
                logger.info(f"ESP32 neckband successfully paired and authenticated. Session: {self.session_id}")
                return LinkProtocolPacket.encode_packet(MsgType.HANDSHAKE_AUTH, {"status": "authenticated"})
            else:
                logger.warning("Pairing challenge verification failed!")
                self.is_connected = False
                return LinkProtocolPacket.encode_packet(MsgType.HANDSHAKE_AUTH, {"status": "auth_failed"})

        # Guard: Reject subsequent data if not authenticated
        if not self.is_connected and msg_type not in (MsgType.HANDSHAKE_HELLO, MsgType.HANDSHAKE_AUTH):
            logger.warning(f"Rejected packet type {msg_type.name}: client not authenticated.")
            return None

        # 3. Heartbeat Ping / Pong
        if msg_type == MsgType.HEARTBEAT_PING:
            self.last_heartbeat_time = time.time()
            return LinkProtocolPacket.encode_packet(MsgType.HEARTBEAT_PONG, {"ack_time": time.time()})

        # 4. Camera Frame Streaming (in ACTIVE state only)
        elif msg_type == MsgType.FRAME_STREAM:
            self.last_heartbeat_time = time.time()
            zone = metadata.get("zone", "Living Room")
            cell = tuple(metadata.get("cell", (4, 2)))
            seed_key = metadata.get("seed_key")

            res = self.face_engine.process_frame(
                image_data=binary_body,
                seed_key=seed_key,
                zone=zone,
                cell=cell,
            )

            # If announcement produced, stream back to neckband speaker
            if res and res.get("announcement") and self.on_speaker_dispatch:
                self.on_speaker_dispatch(res["announcement"])

            return LinkProtocolPacket.encode_packet(
                MsgType.FRAME_STREAM,
                {"status": "processed", "match": res.get("match", False), "announcement": res.get("announcement")}
            )

        # 5. Audio Chunk Streaming (in ACTIVE state only)
        elif msg_type == MsgType.AUDIO_CHUNK:
            self.last_heartbeat_time = time.time()
            sim_trans = metadata.get("simulated_transcript")
            person_id = metadata.get("person_id")
            person_label = metadata.get("person_label")

            res = self.conversation_pipeline.process_audio_chunk(
                audio_bytes=binary_body,
                person_id=person_id,
                person_label=person_label,
                simulated_transcript=sim_trans,
            )
            return LinkProtocolPacket.encode_packet(MsgType.AUDIO_CHUNK, res)

        # 6. Outside Surroundings Check Sample
        elif msg_type == MsgType.OUTSIDE_SAMPLE:
            self.last_heartbeat_time = time.time()
            classification = self.scene_classifier.classify_scene(
                audio_sample=binary_body,
                metadata=metadata,
            )
            resp_meta = {
                "timestamp": time.time(),
                "classification": classification,  # 'PRIVATE', 'NOT_PRIVATE', 'UNDECIDED'
            }
            return LinkProtocolPacket.encode_packet(MsgType.OUTSIDE_RESULT, resp_meta)

        # 7. Emergency Alert Received from ESP32
        elif msg_type == MsgType.EMERGENCY_ALERT:
            self.last_heartbeat_time = time.time()
            alert = EmergencyAlert(
                id=metadata.get("id"),
                timestamp=metadata.get("timestamp", time.time()),
                pulse_bpm=metadata.get("pulse_bpm", 72.0),
                motion_status=metadata.get("motion_status", "normal"),
                location_zone=metadata.get("zone"),
                grid_cell=tuple(metadata.get("cell", (0, 0))) if metadata.get("cell") else None,
                gps_coords=metadata.get("gps"),
                severity=metadata.get("severity", "CRITICAL"),
                resolved=False,
                trigger_reason=metadata.get("trigger_reason", "Vitals alert"),
            )
            self.storage.save_alert(alert)
            return LinkProtocolPacket.encode_packet(MsgType.EMERGENCY_ALERT, {"status": "saved"})

        # 8. State Change Log
        elif msg_type == MsgType.STATE_CHANGE_LOG:
            self.last_heartbeat_time = time.time()
            log_entry = PrivacyLogEntry(
                timestamp=metadata.get("timestamp", time.time()),
                state=PrivacyState(metadata.get("state", "SLEEP")),
                is_inside=bool(metadata.get("is_inside", True)),
                zone=metadata.get("zone"),
                cell_row=metadata.get("cell_row"),
                cell_col=metadata.get("cell_col"),
                reason=metadata.get("reason", "Firmware transition"),
            )
            self.storage.save_privacy_log(log_entry)
            return LinkProtocolPacket.encode_packet(MsgType.STATE_CHANGE_LOG, {"status": "logged"})

        return None

    def check_link_liveness(self, current_time: Optional[float] = None) -> bool:
        """Checks if link is alive. Returns False if timeout exceeded (link loss)."""
        now = current_time or time.time()
        if self.is_connected and (now - self.last_heartbeat_time) > self.heartbeat_timeout:
            logger.warning("Heartbeat timeout exceeded. Marking ESP32 neckband link as DISCONNECTED.")
            self.is_connected = False
            return False
        return self.is_connected
