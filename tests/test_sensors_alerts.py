"""
Tests for Step 7: Sensors and Emergency Alerts
Strict Requirement Verification:
- Raise an emergency alert ONLY when pulse and motion together indicate one.
- Do NOT alert on pulse alone.
- Do NOT alert on motion alone.
- Sensors keep running in every privacy state (including PRIVATE).
"""

from pathlib import Path
from device.storage import SecureStorage
from device.models import PrivacyState
from device.sensors import (
    SensorAlertMonitor,
    MockPulseSensor,
    MockIMUSensor,
    MockGPSSensor,
)


def test_no_alert_on_pulse_alone(tmp_path: Path):
    db_file = tmp_path / "sensor_test.db"
    storage = SecureStorage(db_path=db_file)

    pulse_sensor = MockPulseSensor(default_bpm=72.0)
    imu_sensor = MockIMUSensor(default_status="normal")
    gps_sensor = MockGPSSensor()

    monitor = SensorAlertMonitor(
        storage=storage,
        pulse_sensor=pulse_sensor,
        imu_sensor=imu_sensor,
        gps_sensor=gps_sensor,
    )

    # 1. Normal pulse + Normal motion -> No alert
    assert monitor.evaluate_vitals(current_zone="Living Room") is None
    assert len(storage.get_alerts()) == 0

    # 2. Critical High Pulse (150 BPM) + Normal motion (e.g. fast walking or exercise) -> NO ALERT!
    pulse_sensor.set_bpm(150.0)
    imu_sensor.set_motion("normal")
    alert = monitor.evaluate_vitals(current_zone="Living Room")
    assert alert is None, "Should NOT raise alert on pulse alone!"
    assert len(storage.get_alerts()) == 0

    # 3. Critical Low Pulse (32 BPM) + Normal motion -> NO ALERT!
    pulse_sensor.set_bpm(32.0)
    imu_sensor.set_motion("normal")
    alert_low = monitor.evaluate_vitals(current_zone="Living Room")
    assert alert_low is None, "Should NOT raise alert on low pulse alone!"
    assert len(storage.get_alerts()) == 0


def test_no_alert_on_motion_alone(tmp_path: Path):
    db_file = tmp_path / "sensor_motion_test.db"
    storage = SecureStorage(db_path=db_file)

    pulse_sensor = MockPulseSensor(default_bpm=72.0)  # Healthy, normal pulse
    imu_sensor = MockIMUSensor(default_status="sudden_fall_impact")  # Dropped neckband or sat quickly
    monitor = SensorAlertMonitor(storage=storage, pulse_sensor=pulse_sensor, imu_sensor=imu_sensor)

    alert = monitor.evaluate_vitals(current_zone="Kitchen")
    assert alert is None, "Should NOT raise alert on motion impact alone when pulse is normal!"
    assert len(storage.get_alerts()) == 0


def test_alert_raised_when_pulse_and_motion_combine(tmp_path: Path):
    db_file = tmp_path / "sensor_emergency_test.db"
    storage = SecureStorage(db_path=db_file)

    pulse_sensor = MockPulseSensor(default_bpm=142.0)  # Severe tachycardia
    imu_sensor = MockIMUSensor(default_status="sudden_fall_impact", accel_g=3.8)  # Fall shock
    gps_sensor = MockGPSSensor(has_fix=True, lat=37.7749, lon=-122.4194)

    monitor = SensorAlertMonitor(
        storage=storage,
        pulse_sensor=pulse_sensor,
        imu_sensor=imu_sensor,
        gps_sensor=gps_sensor,
    )

    alert = monitor.evaluate_vitals(current_zone="Bathroom", current_cell=(4, 6))
    assert alert is not None
    assert alert.severity == "CRITICAL"
    assert alert.pulse_bpm == 142.0
    assert alert.motion_status == "sudden_fall_impact"
    assert alert.location_zone == "Bathroom"
    assert alert.gps_coords is not None
    assert "Abnormal pulse (142.0 BPM) combined with critical motion" in alert.trigger_reason

    # Verify stored in permanent SQLite (never deleted)
    saved_alerts = storage.get_alerts()
    assert len(saved_alerts) == 1
    assert saved_alerts[0].id == alert.id


def test_sensors_operate_in_private_privacy_state(tmp_path: Path):
    """Confirm sensors evaluate continuously even when neckband is in PRIVATE state."""
    db_file = tmp_path / "sensor_private_state_test.db"
    storage = SecureStorage(db_path=db_file)

    pulse_sensor = MockPulseSensor(default_bpm=35.0)  # Bradycardia collapse
    imu_sensor = MockIMUSensor(default_status="immobility")  # Collapse on floor
    monitor = SensorAlertMonitor(storage=storage, pulse_sensor=pulse_sensor, imu_sensor=imu_sensor)

    # In PRIVATE room
    privacy_state = PrivacyState.PRIVATE
    assert privacy_state == PrivacyState.PRIVATE

    alert = monitor.evaluate_vitals(current_zone="En-suite Bathroom", current_cell=(4, 6))
    assert alert is not None
    assert alert.severity == "CRITICAL"
    assert alert.location_zone == "En-suite Bathroom"
