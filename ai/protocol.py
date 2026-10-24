"""
Link Protocol framing, serialization, and cryptographic mutual authentication
between ESP32 Neckband and Python AI Service.
Spec: docs/LINK_PROTOCOL.md
"""

from __future__ import annotations
import hmac
import hashlib
import struct
import json
import zlib
import time
from enum import IntEnum
from typing import Tuple, Dict, Any, Optional

MAGIC_HEADER = 0x534D  # 'SM' in ASCII
PROTOCOL_VERSION = 0x01


class MsgType(IntEnum):
    HANDSHAKE_HELLO = 0x01
    HANDSHAKE_AUTH = 0x02
    HEARTBEAT_PING = 0x03
    HEARTBEAT_PONG = 0x04
    FRAME_STREAM = 0x10
    AUDIO_CHUNK = 0x11
    SENSOR_TELEMETRY = 0x12
    EMERGENCY_ALERT = 0x13
    OUTSIDE_SAMPLE = 0x14
    OUTSIDE_RESULT = 0x15
    STATE_CHANGE_LOG = 0x20
    SYNC_SETTINGS = 0x21
    SPEAKER_PLAYBACK = 0x22


class LinkProtocolPacket:
    HEADER_FORMAT = "!HBBHHII"  # Magic(2), Version(1), MsgType(1), Flags(2), SeqNo(2), PayloadLen(4), CRC32(4)
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

    @staticmethod
    def encode_packet(
        msg_type: MsgType,
        metadata: Dict[str, Any],
        binary_payload: Optional[bytes] = None,
        seq_no: int = 0,
        flags: int = 0
    ) -> bytes:
        meta_bytes = json.dumps(metadata).encode("utf-8")
        meta_len = len(meta_bytes)
        bin_body = binary_payload or b""

        # Payload is: [MetaLen: uint32][MetaBytes][BinaryBody]
        payload = struct.pack("!I", meta_len) + meta_bytes + bin_body
        payload_len = len(payload)
        checksum = zlib.crc32(payload) & 0xFFFFFFFF

        header = struct.pack(
            LinkProtocolPacket.HEADER_FORMAT,
            MAGIC_HEADER,
            PROTOCOL_VERSION,
            int(msg_type),
            flags,
            seq_no,
            payload_len,
            checksum
        )
        return header + payload

    @staticmethod
    def decode_packet(data: bytes) -> Tuple[MsgType, Dict[str, Any], bytes, int]:
        """
        Decodes a packet.
        Returns (msg_type, metadata_dict, binary_body, seq_no).
        Raises ValueError on corruption or checksum mismatch.
        """
        if len(data) < LinkProtocolPacket.HEADER_SIZE:
            raise ValueError("Packet smaller than header size.")

        header = data[:LinkProtocolPacket.HEADER_SIZE]
        magic, ver, mtype, flags, seq, payload_len, expected_crc = struct.unpack(
            LinkProtocolPacket.HEADER_FORMAT, header
        )

        if magic != MAGIC_HEADER:
            raise ValueError(f"Invalid magic header: {hex(magic)}")
        if ver != PROTOCOL_VERSION:
            raise ValueError(f"Unsupported protocol version: {ver}")

        payload = data[LinkProtocolPacket.HEADER_SIZE:LinkProtocolPacket.HEADER_SIZE + payload_len]
        if len(payload) != payload_len:
            raise ValueError(f"Incomplete payload: expected {payload_len}, got {len(payload)}")

        actual_crc = zlib.crc32(payload) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError(f"CRC checksum mismatch: {actual_crc} != {expected_crc}")

        meta_len = struct.unpack("!I", payload[:4])[0]
        meta_bytes = payload[4:4 + meta_len]
        binary_body = payload[4 + meta_len:]

        metadata = json.loads(meta_bytes.decode("utf-8")) if meta_len > 0 else {}
        return MsgType(mtype), metadata, binary_body, seq


class LinkAuthenticator:
    """Mutual challenge-response authentication using Pre-Shared Key (PSK)."""

    def __init__(self, psk: str = "smart_memory_neckband_psk_shared_key_32b_fixed"):
        self.psk = psk.encode("utf-8")

    def generate_challenge(self, nonce: str) -> str:
        return hmac.new(self.psk, nonce.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify_challenge(self, nonce: str, expected_hmac: str) -> bool:
        computed = self.generate_challenge(nonce)
        return hmac.compare_digest(computed, expected_hmac)
