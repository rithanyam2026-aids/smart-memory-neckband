"""
Comprehensive tests for 3-state Privacy State Machine:
- Entering and leaving private areas set in dashboard
- Waking on person / speech
- Returning to SLEEP on person leaving / silence timeout
- Leaving house through an exit cell to OUTSIDE
- Outside check detecting a toilet-like private place -> PRIVATE
- Returning to SLEEP when no longer private
- Treating an undecided check as PRIVATE (fail-safe)
- Treating unresolved position as OUTSIDE
- Pulse and IMU sensors keep running in every state
"""

from pathlib import Path
from device.models import PrivacyState, LocationState
from device.grid import HouseGridLoader, PrivateAreaManager
from device.storage import SecureStorage
from device.privacy import PrivacyStateMachine, MockSceneClassifier


def create_test_state_machine(tmp_path: Path) -> Tuple[PrivacyStateMachine, PrivateAreaManager, MockSceneClassifier]:
    db_file = tmp_path / "privacy_test.db"
    storage = SecureStorage(db_path=db_file)
    blueprint_path = Path(__file__).resolve().parent.parent / "data" / "house_grid.sample.json"
    grid = HouseGridLoader.load_from_file(blueprint_path)
    area_mgr = PrivateAreaManager(storage=storage, grid=grid)
    mock_classifier = MockSceneClassifier(default_result="NOT_PRIVATE")
    sm = PrivacyStateMachine(
        grid=grid,
        area_manager=area_mgr,
        storage=storage,
        scene_classifier=mock_classifier,
        silence_timeout_seconds=2.0
    )
    return sm, area_mgr, mock_classifier


def test_initial_state_and_sensor_power(tmp_path: Path):
    sm, _, _ = create_test_state_machine(tmp_path)
    assert sm.state == PrivacyState.SLEEP
    assert sm.location == LocationState.INSIDE
    assert sm.is_camera_powered is False
    assert sm.is_mic_powered is False
    # Sensors keep running in every state
    assert sm.are_sensors_powered is True


def test_inside_private_area_transitions(tmp_path: Path):
    sm, area_mgr, _ = create_test_state_machine(tmp_path)

    # User starts in normal hallway
    sm.update_position(row=6, col=4)
    assert sm.state == PrivacyState.SLEEP

    # Caregiver marks 'Master Bedroom' as private in dashboard
    area_mgr.set_zone_privacy("Master Bedroom", is_private=True, set_by="caregiver")

    # User enters Master Bedroom (row 2, col 6) -> goes to PRIVATE immediately
    sm.update_position(row=2, col=6)
    assert sm.state == PrivacyState.PRIVATE
    assert sm.is_camera_powered is False
    assert sm.is_mic_powered is False
    assert sm.are_sensors_powered is True

    # In PRIVATE, person detected does NOT wake camera/mic
    sm.on_person_detected()
    assert sm.state == PrivacyState.PRIVATE

    # User leaves Master Bedroom back into Hallway (row 5, col 4)
    # MUST return to SLEEP (never straight to ACTIVE)
    sm.update_position(row=5, col=4)
    assert sm.state == PrivacyState.SLEEP
    assert sm.is_camera_powered is False


def test_wake_on_person_and_silence_timeout(tmp_path: Path):
    sm, _, _ = create_test_state_machine(tmp_path)

    # In SLEEP in Living Room (row 4, col 2)
    sm.update_position(row=4, col=2)
    assert sm.state == PrivacyState.SLEEP

    # Face or speech detected -> wakes to ACTIVE
    sm.on_person_detected("Granddaughter entered and started talking")
    assert sm.state == PrivacyState.ACTIVE
    assert sm.is_camera_powered is True
    assert sm.is_mic_powered is True

    # Person leaves -> returns to SLEEP
    sm.on_person_left_or_silence()
    assert sm.state == PrivacyState.SLEEP
    assert sm.is_camera_powered is False


def test_exit_house_and_outside_toilet_check(tmp_path: Path):
    sm, _, mock_classifier = create_test_state_machine(tmp_path)

    # User walks to exit door at (7, 4)
    sm.update_position(row=7, col=4)
    assert sm.location == LocationState.INSIDE

    # User steps outside the grid boundary through the exit door
    sm.update_position(row=8, col=4)
    assert sm.location == LocationState.OUTSIDE
    assert sm.state == PrivacyState.SLEEP

    # Outside surroundings check detects a public restroom / toilet
    mock_classifier.set_result("PRIVATE")
    sm.check_outside_surroundings(force=True)
    assert sm.state == PrivacyState.PRIVATE
    assert sm.is_camera_powered is False
    assert sm.is_mic_powered is False

    # Still in private restroom -> stays in PRIVATE
    sm.check_outside_surroundings(force=True)
    assert sm.state == PrivacyState.PRIVATE

    # User exits restroom into outdoor park
    mock_classifier.set_result("NOT_PRIVATE")
    sm.check_outside_surroundings(force=True)
    assert sm.state == PrivacyState.SLEEP

    # In outdoor park, meets neighbor -> wakes to ACTIVE
    sm.on_person_detected("Neighbor greeted")
    assert sm.state == PrivacyState.ACTIVE

    # Returns to SLEEP after conversation
    sm.on_person_left_or_silence()
    assert sm.state == PrivacyState.SLEEP

    # Scene check cannot decide (uncertain) -> treats as PRIVATE (fail-safe)
    mock_classifier.set_result("UNDECIDED")
    sm.check_outside_surroundings(force=True)
    assert sm.state == PrivacyState.PRIVATE


def test_unresolvable_position_treated_as_outside(tmp_path: Path):
    sm, _, _ = create_test_state_machine(tmp_path)
    # Position cannot be resolved (None, None) -> treated as OUTSIDE
    sm.update_position(row=None, col=None)
    assert sm.location == LocationState.OUTSIDE
    # Failsafe defaults safely
    assert sm.state in (PrivacyState.SLEEP, PrivacyState.PRIVATE)
