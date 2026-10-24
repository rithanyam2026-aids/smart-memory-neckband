"""
Hardware Sensors Module for Smart Memory Neckband.
Implements:
- Pulse sensor, 6-axis IMU (motion), and optional GPS behind clean hardware interfaces
- Mock modes for all sensors so the system runs and tests on any laptop/PC
- Combined Emergency Alert Rule:
  "Raise an emergency alert only when pulse and motion together indicate one. Do not alert on pulse alone."
- Continuous operation: Sensors keep running in every privacy state (PRIVATE, SLEEP, ACTIVE).
"""

from __future__ import annotations
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple

from device.models import EmergencyAlert
from device.storage import SecureStorage

logger = logging.getLogger("Sensors")


# --- Sensor Interfaces & Mocks ---
class PulseSensorInterface(ABC):
    @abstractmethod
    def read_pulse(self) -> float:
        """Returns heart rate in beats per minute (BPM)."""
        pass


class MockPulseSensor(PulseSensorInterface):
    def __init__(self, default_bpm: float = 72.0):
        self.bpm = default_bpm

    def set_bpm(self, bpm: float):
        self.bpm = bpm

    def read_pulse(self) -> float:
        return self.bpm


class IMUSensorInterface(ABC):
    @abstractmethod
    def read_motion(self) -> Dict[str, Any]:
        """Returns motion dynamics: status ('normal', 'sudden_fall_impact', 'immobility'), acceleration magnitude."""
        pass


class MockIMUSensor(IMUSensorInterface):
    def __init__(self, default_status: str = "normal", accel_g: float = 1.0):
        self.status = default_status
        self.accel_g = accel_g

    def set_motion(self, status: str, accel_g: float = 1.0):
        self.status = status
        self.accel_g = accel_g

    def read_motion(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "accel_g": self.accel_g,
            "gyro_deg_s": 0.0,
        }


class GPSSensorInterface(ABC):
    @abstractmethod
    def read_coordinates(self) -> Optional[Dict[str, float]]:
        """Returns {'latitude': float, 'longitude': float} or None if indoors/no fix."""
        pass


class MockGPSSensor(GPSSensorInterface):
    def __init__(self, has_fix: bool = True, lat: float = 37.7749, lon: float = -122.4194):
        self.has_fix = has_fix
        self.lat = lat
        self.lon = lon

    def set_fix(self, has_fix: bool, lat: float = 37.7749, lon: float = -122.4194):
        self.has_fix = has_fix
        self.lat = lat
        self.lon = lon

    def read_coordinates(self) -> Optional[Dict[str, float]]:
        if not self.has_fix:
            return None
        return {"latitude": self.lat, "longitude": self.lon}


# --- Emergency Alert Monitor ---
class SensorAlertMonitor:
    """
    Monitors pulse and motion in all privacy states.
    Strict medical rule:
    - Pulse spike or collapse ALONE does NOT alert (e.g. running or temporary misread).
    - Motion impact ALONE does NOT alert (e.g. sitting down quickly or dropping device).
    - Emergency alert is raised ONLY when abnormal pulse AND severe motion together occur.
    """

    CRITICAL_HIGH_PULSE = 130.0  # BPM
    CRITICAL_LOW_PULSE = 40.0   # BPM

    def __init__(
        self,
        storage: SecureStorage,
        pulse_sensor: Optional[PulseSensorInterface] = None,
        imu_sensor: Optional[IMUSensorInterface] = None,
        gps_sensor: Optional[GPSSensorInterface] = None,
    ):
        self.storage = storage
        self.pulse_sensor = pulse_sensor or MockPulseSensor()
        self.imu_sensor = imu_sensor or MockIMUSensor()
        self.gps_sensor = gps_sensor or MockGPSSensor()
        self.last_alert_time: float = 0.0

    def evaluate_vitals(
        self,
        current_zone: Optional[str] = None,
        current_cell: Optional[Tuple[int, int]] = None,
    ) -> Optional[EmergencyAlert]:
        """
        Poll sensors and determine if combined vitals warrant an emergency dispatch.
        """
        bpm = self.pulse_sensor.read_pulse()
        motion = self.imu_sensor.read_motion()
        gps = self.gps_sensor.read_coordinates()

        is_pulse_abnormal = (bpm >= self.CRITICAL_HIGH_PULSE or bpm <= self.CRITICAL_LOW_PULSE)
        motion_status = motion.get("status", "normal")
        is_motion_critical = motion_status in ("sudden_fall_impact", "immobility", "severe_impact")

        # STRICT RULE: ONLY alert when pulse AND motion together indicate emergency!
        if is_pulse_abnormal and is_motion_critical:
            reason = (
                f"Abnormal pulse ({bpm:.1f} BPM) combined with critical motion ({motion_status}, {motion.get('accel_g', 0)}g)"
            )
            alert = EmergencyAlert(
                timestamp=time.time(),
                pulse_bpm=bpm,
                motion_status=motion_status,
                location_zone=current_zone,
                grid_cell=current_cell,
                gps_coords=gps,
                severity="CRITICAL",
                resolved=False,
                trigger_reason=reason,
                sync_status="pending",
            )
            # Save to permanent secure SQLite (never auto-deleted)
            self.storage.save_alert(alert)
            self.last_alert_time = time.time()
            logger.warning(f"🚨 EMERGENCY ALERT RAISED: {reason}")
            return alert

        elif is_pulse_abnormal and not is_motion_critical:
            logger.info(f"Abnormal pulse ({bpm:.1f} BPM) detected, but normal motion. Pulse alone does NOT trigger emergency.")
            return None

        elif is_motion_critical and not is_pulse_abnormal:
            logger.info(f"Motion event ({motion_status}) detected, but pulse is normal ({bpm:.1f} BPM). Motion alone does NOT trigger emergency.")
            return None

        return None
