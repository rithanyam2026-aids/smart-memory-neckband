# ESP32 Neckband <-> Phone AI Service Link Protocol Specification
**Document Version:** 1.0.0  
**Status:** Approved Architecture  

---

## 1. Overview & Transport Layer

The Smart Memory Neckband (ESP32-S3) communicates with the Python AI Service running on the user's smartphone (or laptop during development) over a high-speed, local Wi-Fi link (via phone mobile hotspot or local home network). **No internet connection is required.**

### Transport
- **Protocol:** WebSocket over TLS (`wss://`) or TCP socket with AES-GCM framing.
- **Port:** `8765` (configurable).
- **Format:** Framed binary envelopes with JSON metadata headers and raw binary payload (JPEG frames, PCM audio chunks).
- **Heartbeat & Link Loss Detection:** Ping/Pong every `1000ms`. If no pong is received within `2500ms`, link loss is triggered immediately.

---

## 2. Pairing & Link Encryption

To ensure **only the authorized user's neckband can connect to their phone AI service**:

1. **Pre-Shared Key (PSK):** Both the ESP32 flash and the phone AI service config store a 32-byte secret key (`LINK_PRESHARED_KEY`).
2. **Handshake & Mutual Authentication:**
   ```
   ESP32 (Client)                                   Phone AI Service (Host)
        |                                                      |
        |---- 1. Hello { device_id, nonce_c, timestamp } ----->|
        |                                                      |
        |<--- 2. Challenge { nonce_s, hmac(PSK, nonce_c) } ----|
        |                                                      |
        |---- 3. Auth { hmac(PSK, nonce_s), session_id } ------>|
        |                                                      |
        |<=== 4. Connection Established (Session Key Derived) =|
   ```
3. **Session Encryption:**
   All subsequent messages are authenticated and encrypted using **AES-128-GCM** (or TLS 1.3), using a session key derived via HKDF-SHA256 from `PSK + nonce_c + nonce_s`.

---

## 3. Message Envelope Format

Every packet exchanged over the link follows a uniform 16-byte header followed by JSON metadata and optional binary payload:

```
+-------------------------------------------------------------------+
| Magic (2B) | Version (1B) | MsgType (1B) | Flags (2B) | SeqNo (2B)|
| 0x53 0x4D  | 0x01         | uint8        | uint16     | uint16    |
+-------------------------------------------------------------------+
| Payload Length (4B, uint32)   | Header Checksum (4B, CRC32)       |
+-------------------------------------------------------------------+
| Payload (Encrypted JSON metadata + Binary Body: JPEG/PCM/Vitals)  |
+-------------------------------------------------------------------+
```

### Message Types (`MsgType`):
| Code | Identifier | Direction | Description |
|------|------------|-----------|-------------|
| `0x01` | `HANDSHAKE_HELLO` | ESP32 -> AI | Client pairing initiation |
| `0x02` | `HANDSHAKE_AUTH` | AI <-> ESP32 | Challenge-response authentication |
| `0x03` | `HEARTBEAT_PING` | ESP32 -> AI | Periodic 1-second keepalive |
| `0x04` | `HEARTBEAT_PONG` | AI -> ESP32 | Keepalive acknowledgment & latency check |
| `0x10` | `FRAME_STREAM` | ESP32 -> AI | Camera JPEG frame (only when person likely present in ACTIVE) |
| `0x11` | `AUDIO_CHUNK` | ESP32 -> AI | PCM 16kHz audio stream (only in ACTIVE state) |
| `0x12` | `SENSOR_TELEMETRY` | ESP32 -> AI | Pulse BPM, IMU status, GPS coords, Battery % |
| `0x13` | `EMERGENCY_ALERT` | ESP32 -> AI | Emergency fall/shock + pulse collapse notification |
| `0x14` | `OUTSIDE_SAMPLE` | ESP32 -> AI | Short 200ms audio/visual sample for toilet check |
| `0x15` | `OUTSIDE_RESULT` | AI -> ESP32 | Scene classification result (`PRIVATE`, `NOT_PRIVATE`, `UNDECIDED`) |
| `0x20` | `STATE_CHANGE_LOG` | ESP32 -> AI | Privacy state machine transition log entry |
| `0x21` | `SYNC_SETTINGS` | AI -> ESP32 | Downstream private rooms, grid coordinates, thresholds |
| `0x22` | `SPEAKER_PLAYBACK` | AI -> ESP32 | TTS audio stream or canned prompt to play on neckband speaker |

---

## 4. Message Payloads Specification

### 4.1 Camera Frame (`0x10` - `FRAME_STREAM`)
- **Condition:** Streamed only when the neckband is in `ACTIVE` state and person motion/face contour is detected.
- **Metadata (JSON):**
  ```json
  {
    "timestamp": 1792840120.45,
    "zone": "Living Room",
    "cell": [4, 2],
    "width": 640,
    "height": 480,
    "format": "JPEG"
  }
  ```
- **Binary Body:** Compressed JPEG frame bytes.
- **Privacy Rule:** ESP32 never stores frames in flash. AI service extracts embeddings and immediately zeros/deletes the image bytes.

### 4.2 Audio Chunk (`0x11` - `AUDIO_CHUNK`)
- **Condition:** Streamed only when the neckband is in `ACTIVE` state.
- **Metadata (JSON):**
  ```json
  {
    "timestamp": 1792840120.50,
    "sample_rate": 16000,
    "channels": 1,
    "bits_per_sample": 16,
    "duration_ms": 500
  }
  ```
- **Binary Body:** 16-bit Mono Linear PCM audio buffer.
- **Privacy Rule:** AI service transcribes via Whisper and deletes raw audio immediately.

### 4.3 Outside Check Sample (`0x14` - `OUTSIDE_SAMPLE`)
- **Condition:** Streamed when outside the house at configurable intervals (e.g., every 10 seconds).
- **Metadata (JSON):**
  ```json
  {
    "timestamp": 1792840130.00,
    "sample_type": "SURROUNDINGS_CHECK",
    "duration_ms": 200
  }
  ```
- **Binary Body:** 200ms audio snippet + low-res scene snapshot (JPEG).
- **Response (`0x15` - `OUTSIDE_RESULT`):**
  ```json
  {
    "timestamp": 1792840130.18,
    "classification": "PRIVATE", // "PRIVATE" | "NOT_PRIVATE" | "UNDECIDED"
    "confidence": 0.92,
    "detected_scene": "restroom_acoustics"
  }
  ```

### 4.4 Emergency Alert (`0x13` - `EMERGENCY_ALERT`)
- **Condition:** Triggered **only** when pulse AND motion together indicate emergency.
- **Payload (JSON):**
  ```json
  {
    "id": "alert_esp32_1792840145",
    "timestamp": 1792840145.22,
    "pulse_bpm": 146.5,
    "motion_status": "sudden_fall_impact",
    "accel_magnitude_g": 3.9,
    "zone": "En-suite Bathroom",
    "cell": [4, 6],
    "gps": { "latitude": 37.7749, "longitude": -122.4194 },
    "trigger_reason": "Severe fall with rapid pulse spike"
  }
  ```

### 4.5 Downstream Settings Sync (`0x21` - `SYNC_SETTINGS`)
- **Sent by AI Service when settings change on the dashboard:**
  ```json
  {
    "version": 104,
    "private_zones": ["Master Bedroom", "En-suite Bathroom"],
    "private_cells": [[1, 2]],
    "outside_check_interval_sec": 10.0,
    "outside_sample_duration_ms": 200
  }
  ```
- **Saved into ESP32 LittleFS flash** so the neckband keeps working completely offline even if disconnected.

---

## 5. Fail-Safe Link Drop & Reconnection Behavior

1. **Heartbeat Loss:**
   If the ESP32 misses 2 consecutive keepalive responses (`> 2500ms`):
   - The ESP32 immediately cuts off the camera and microphone power gate and transitions to **`PRIVATE` or `SLEEP`**.
   - **Under no circumstances does the ESP32 remain in `ACTIVE` state when disconnected.**
2. **Reconnection:**
   - ESP32 enters exponential retry backoff (1s, 2s, 4s, 8s, up to 15s max).
   - Once the local Wi-Fi / hotspot socket is restored, re-executes mutual authentication handshake (`0x01` / `0x02`).
   - Resumes normal operation using the last saved flash settings.
