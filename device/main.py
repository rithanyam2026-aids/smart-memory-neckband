"""
Main Runtime Orchestrator for Smart Memory Neckband.
Coordinates:
- Secure local SQLite storage
- House grid and dynamic private areas
- 3-state Privacy State Machine (PRIVATE, SLEEP, ACTIVE)
- Face recognition engine (cosine similarity, embedding averaging, unknown-to-familiar promotion)
- Pulse and IMU sensors with combined emergency alert rules
- Camera and microphone hardware abstractions with mock modes
- Offline sync queue with cloud backend
"""

from __future__ import annotations
import time
import logging
from typing import Optional, Dict, Any, Tuple

from device.config import config
from device.storage import SecureStorage
from device.grid import HouseGridLoader, HouseGrid, PrivateAreaManager
from device.privacy import PrivacyStateMachine, MockSceneClassifier
from device.face_recognition import FaceRecognitionEngine
from device.sensors import SensorAlertMonitor, MockPulseSensor, MockIMUSensor, MockGPSSensor
from device.camera import MockCamera
from device.audio import MockMicrophone, MockVoiceOutput
from device.sync_client import SyncClient
from device.models import PrivacyState, DeviceTelemetry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("NeckbandDevice")


class SmartMemoryNeckband:
    def __init__(
        self,
        db_path: Optional[str] = None,
        blueprint_path: Optional[str] = None,
        cloud_url: Optional[str] = None,
    ):
        # 1. Storage & Config
        self.storage = SecureStorage(db_path=db_path)

        # 2. House Blueprint & Dynamic Private Areas
        self.grid: HouseGrid = HouseGridLoader.load_from_file(blueprint_path)
        self.area_manager = PrivateAreaManager(storage=self.storage, grid=self.grid)

        # 3. Privacy State Machine
        self.scene_classifier = MockSceneClassifier(default_result="NOT_PRIVATE")
        self.privacy_machine = PrivacyStateMachine(
            grid=self.grid,
            area_manager=self.area_manager,
            storage=self.storage,
            scene_classifier=self.scene_classifier,
        )

        # 4. Face Recognition Engine
        self.face_engine = FaceRecognitionEngine(storage=self.storage)

        # 5. Hardware Sensors & Alert Monitor
        self.pulse_sensor = MockPulseSensor(default_bpm=72.0)
        self.imu_sensor = MockIMUSensor(default_status="normal")
        self.gps_sensor = MockGPSSensor(has_fix=True)
        self.alert_monitor = SensorAlertMonitor(
            storage=self.storage,
            pulse_sensor=self.pulse_sensor,
            imu_sensor=self.imu_sensor,
            gps_sensor=self.gps_sensor,
        )

        # 6. Audio, Camera, Voice Output
        self.camera = MockCamera()
        self.microphone = MockMicrophone()
        self.speaker = MockVoiceOutput()

        # 7. Sync Client
        self.sync_client = SyncClient(
            storage=self.storage,
            cloud_url=cloud_url or config.CLOUD_API_URL
        )

        logger.info("Smart Memory Neckband initialized successfully.")

    def step(
        self,
        row: Optional[int] = None,
        col: Optional[int] = None,
        face_detected_key: Optional[str] = None,
        speech_detected: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute one operational cycle:
        1. Evaluate Pulse + Motion sensors (runs in ALL privacy states)
        2. Update physical position on house grid or outside
        3. Check microphone VAD or face trigger to wake to ACTIVE
        4. If ACTIVE: capture face, run matching, announce person, capture speech
        5. Flush sync queue if network is reachable
        """
        # Step 1: Vitals & Combined Emergency Alert (Continuous in all states)
        alert = self.alert_monitor.evaluate_vitals(
            current_zone=self.privacy_machine.current_zone,
            current_cell=self.privacy_machine.current_cell,
        )

        # Step 2: Update position & privacy machine
        if row is not None or col is not None:
            self.privacy_machine.update_position(row, col)

        # Step 3: Check wake triggers if someone is present
        if face_detected_key or speech_detected:
            self.privacy_machine.on_person_detected("Encountered face or voice")

        # Step 4: If ACTIVE, process face & speech
        recognition_result = None
        if self.privacy_machine.state == PrivacyState.ACTIVE:
            if face_detected_key:
                frame_data = self.camera.capture_frame(self.privacy_machine.state)
                recognition_result = self.face_engine.process_face(
                    image_data=frame_data,
                    seed_key=face_detected_key,
                    zone=self.privacy_machine.current_zone,
                    cell=self.privacy_machine.current_cell,
                )
                if recognition_result and recognition_result.get("announcement"):
                    self.speaker.speak(recognition_result["announcement"])

        telemetry = DeviceTelemetry(
            device_id=config.DEVICE_ID,
            battery_pct=96.5,
            privacy_state=self.privacy_machine.state,
            is_inside=(self.privacy_machine.location.value == "INSIDE"),
            current_zone=self.privacy_machine.current_zone,
            grid_cell=self.privacy_machine.current_cell,
            camera_active=self.privacy_machine.is_camera_powered,
            mic_active=self.privacy_machine.is_mic_powered,
            sensors_active=self.privacy_machine.are_sensors_powered,
        )

        return {
            "privacy_state": self.privacy_machine.state.value,
            "location": self.privacy_machine.location.value,
            "current_zone": self.privacy_machine.current_zone,
            "emergency_alert": alert,
            "recognition": recognition_result,
            "telemetry": telemetry,
        }


if __name__ == "__main__":
    neckband = SmartMemoryNeckband()
    logger.info("Executing simulated startup cycle...")
    result = neckband.step(row=3, col=2, face_detected_key="ananya")
    logger.info(f"Cycle result: {result}")
