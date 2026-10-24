# Smart Memory Neckband (ESP32-S3 + Phone AI Architecture)

A privacy-first, offline-capable smart memory neckband powered by an **ESP32-S3 microcontroller** (sensors and hardware privacy gates) communicating over a secure local Wi-Fi link with a **Python AI Service** running offline on the user's smartphone (or laptop during development), with a responsive web dashboard for the senior user and their caregiver.

---

## 🏗️ Hardware Architecture & System Split

```
+-------------------------------------------------------------------------+
|                        NECKBAND HARDWARE (/firmware)                    |
|                        ESP32-S3 with 8MB PSRAM                          |
| - Hardware Privacy Power Gates (Cut off Camera & Mic in PRIVATE)        |
| - Continuous Vitals: Pulse Sensor & 6-Axis IMU (Emergency Alert Rule)   |
| - Geo-Grid Engine: Blueprint & Private Rooms saved in LittleFS Flash    |
| - Local Link: Encrypted WebSocket/TCP client streaming to Phone AI      |
+-------------------------------------------------------------------------+
                                     │  Local Hotspot / Wi-Fi Link
                                     │  (Pre-Shared Key Mutual Auth,
                                     │   docs/LINK_PROTOCOL.md)
                                     ▼
+-------------------------------------------------------------------------+
|                     USER'S PHONE AI SERVICE (/ai)                       |
|          Runs in background via Chaquopy on Android (or Laptop)         |
| - Face Recognition (OpenCV + FaceNet embeddings, instant frame purge)   |
| - Offline Whisper Speech-to-Text & LLM Note Extractor (Skips casual)   |
| - Swappable Scene Classifier (Acoustic tile echo + restroom detection)  |
| - Offline TTS (Reminders & daily summary spoken aloud)                  |
| - Encrypted SQLite Storage (Strangers ~30d, Notes 60d, Alerts kept)     |
+-------------------------------------------------------------------------+
                                     │  Optional HTTPS / MQTT Sync
                                     ▼
+-------------------------------------------------------------------------+
|                          CLOUD BACKEND (/cloud)                         |
| - SQL Master Database (Audit log of private area changes)               |
| - Role Isolation (Caregiver only sees linked senior user)               |
| - History Search (by Date, Person, and Room Zone)                       |
| - Web Dashboard Static Server (/dashboard)                              |
+-------------------------------------------------------------------------+
```

---

## 🛠️ Framework & Technology Selections

1. **Neckband Firmware: PlatformIO with Arduino-ESP32**
   - *Why*: PlatformIO provides reproducible embedded builds and seamless desktop unit testing. The `arduino-esp32` framework on the ESP32-S3 provides mature, hardware-accelerated drivers for the OV2640 camera (`esp_camera.h`), I2S audio microphone and speaker (`driver/i2s.h`), and LittleFS flash memory for local grid maps and dynamic private room settings.
2. **Android AI Packaging: Chaquopy**
   - *Why*: Chaquopy embeds the standard Python runtime directly into a native Android APK as an always-on background `ForegroundService`. Unlike Termux (which requires a terminal shell and manual launch), Chaquopy runs silently on boot without user interaction, accesses local sockets to the neckband, and runs the exact same Python AI code completely offline.
3. **Outside-the-House Scene Check Method**:
   - *What it looks at and listens for*:
     - **Acoustic Reverberation (RT60)**: Hard ceramic surfaces, plumbing cavitation, running faucets, flush cycles, ventilation exhaust hum.
     - **Visual Geometric Structure**: Tile boundaries, privacy stall partitions, absence of foliage/horizon.
     - **Privacy Guarantee**: Evaluated in-memory over a short 150-200ms sample; sample is purged and zeroed out immediately upon decision.

---

## 📌 ESP32-S3 Hardware Pinout & Wiring

| Peripheral | ESP32-S3 Pin | Description / Wiring Notes |
|------------|--------------|----------------------------|
| **Camera Power Gate** | `GPIO 21` | P-Channel MOSFET Gate. `LOW` = Hard physical cut-off to camera power rail in `PRIVATE` state. |
| **Mic Power Gate** | `GPIO 47` | MOSFET Gate. `LOW` = Hard physical cut-off to INMP441 microphone power rail in `PRIVATE` state. |
| **Status Indicator LED** | `GPIO 48` | NeoPixel / RGB LED: Green (`ACTIVE`), Blue (`SLEEP`), Red (`PRIVATE`). |
| **Pulse Sensor** | `GPIO 1` (ADC1_CH0) | Analog optical PPG pulse sensor (continuous vitals). |
| **6-Axis IMU (MPU6050)** | `GPIO 4` (SDA), `GPIO 5` (SCL) | I2C motion sensor (fall impact & immobility detection). |
| **Optional GPS (NEO-6M)** | `GPIO 19` (RX), `GPIO 20` (TX) | Hardware UART2 GPS receiver. |
| **I2S Microphone (INMP441)**| `GPIO 42` (WS), `GPIO 41` (SCK), `GPIO 2` (SD) | 16kHz mono digital microphone. |
| **I2S Speaker (MAX98357A)** | `GPIO 15` (BCLK), `GPIO 16` (LRC), `GPIO 7` (DIN) | 3W Class-D amplifier driving neckband speaker/earpiece. |

---

## 🔒 Link Protocol & Privacy Fail-Safes

- **Handshake & Mutual Auth:** Authenticates with a 32-byte Pre-Shared Key (PSK) via challenge-response HMAC-SHA256 (`docs/LINK_PROTOCOL.md`).
- **Heartbeat & Link Loss Fail-Safe:** 
  - Ping/Pong every `1000ms`.
  - If the link drops (`> 2500ms` without acknowledgment), the ESP32 firmware **immediately powers down camera and microphone hardware gates and falls back to `PRIVATE` or `SLEEP`**.
  - **The neckband never remains in `ACTIVE` state when disconnected.**
- **Outside Check Fail-Safe:** If the scene classifier cannot decide or the link to the phone is down, the outside venue is treated as **`PRIVATE`**.
- **Combined Vitals Emergency Alert Rule:** An emergency alert is raised **only when abnormal pulse (<40 or >130 BPM) and critical motion (fall impact or immobility) occur together**. Pulse alone never alerts.

---

## 🧪 Testing Without Hardware

The entire system is testable on a computer without physical hardware:
1. **Simulated ESP32 Firmware**: `firmware/simulated_firmware.py` tests power gates, inside/outside grid transitions, private rooms, link loss, and sensor alert logic.
2. **AI Service Testing**: Ingests recorded PCM audio files, synthetic test frames, or real laptop webcam frames (`ai.face_recognition.FaceEmbedder.capture_from_webcam()`).
3. **Full Automated Test Suite**:
   ```bash
   python -m pytest
   ```

---

## 🚀 Running the System

### 1. Run the Python AI Service & Cloud Backend
```bash
python -m uvicorn cloud.server:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Access the Dashboard
Open your browser to [http://localhost:8000/](http://localhost:8000/):
- **USER Mode**: Big tactile buttons, high contrast, today's visitors, reminders, date picker with read-aloud TTS, voice dictation notes, and house map privacy toggling.
- **CAREGIVER Mode**: Neckband status overview, emergency alerts, history queries (by Date, Person, Zone), visitor relationship customizer, reminders scheduler, collaborative notes, house geo-grid map with user location avatar, and private area change audit log.
