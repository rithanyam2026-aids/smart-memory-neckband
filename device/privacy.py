"""
Privacy State Machine and Scene Classification for Smart Memory Neckband.

States:
- PRIVATE: Camera and microphone strictly off (no capture, no recording). Pulse & IMU stay on.
- SLEEP: Low-power sleep. Not saving anything. Waiting for person or outside sample.
- ACTIVE: Capturing and processing (face recognition, voice activity).

Inside House:
- Private area -> PRIVATE immediately.
- Leaving private area -> SLEEP (never straight to ACTIVE).
- SLEEP -> wakes to ACTIVE only when person or speech is encountered.
- ACTIVE -> returns to SLEEP on person departure or silence timeout.

Outside House:
- Default SLEEP.
- Short periodic sample checks surroundings via swappable SceneClassifier.
- Toilet / bathroom / restroom / changing room -> PRIVATE.
- Leaves private place -> returns to SLEEP.
- Undecided -> PRIVATE (fail-safe).
- If inside/outside cannot be determined -> treats as OUTSIDE.
- General failsafe: If anything errors or is unsure, default to PRIVATE or SLEEP, NEVER ACTIVE.
"""

from __future__ import annotations
import time
import logging
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any

from device.config import config
from device.models import PrivacyState, LocationState, PrivacyLogEntry
from device.grid import HouseGrid, PrivateAreaManager
from device.storage import SecureStorage

logger = logging.getLogger("PrivacyStateMachine")


class SceneClassifier(ABC):
    """
    Swappable interface for outside-the-house private venue detection.
    Evaluates in-memory short sample (never saved or transmitted).
    """

    @abstractmethod
    def classify(self, audio_sample: Optional[bytes] = None, image_sample: Optional[Any] = None) -> str:
        """
        Returns one of: 'PRIVATE', 'NOT_PRIVATE', or 'UNDECIDED'.
        Private places include: toilet, restroom, bathroom, changing room.
        """
        pass


class MockSceneClassifier(SceneClassifier):
    """
    Mock classifier for automated testing and simulation.
    Can be configured to return specific classification outcomes.
    """

    def __init__(self, default_result: str = "NOT_PRIVATE"):
        self.next_result = default_result

    def set_result(self, result: str):
        # Result should be 'PRIVATE', 'NOT_PRIVATE', or 'UNDECIDED'
        self.next_result = result

    def classify(self, audio_sample: Optional[bytes] = None, image_sample: Optional[Any] = None) -> str:
        return self.next_result


class PrivacyStateMachine:
    def __init__(
        self,
        grid: HouseGrid,
        area_manager: PrivateAreaManager,
        storage: SecureStorage,
        scene_classifier: Optional[SceneClassifier] = None,
        silence_timeout_seconds: Optional[float] = None,
    ):
        self.grid = grid
        self.area_manager = area_manager
        self.storage = storage
        self.scene_classifier = scene_classifier or MockSceneClassifier()
        self.silence_timeout = silence_timeout_seconds or config.ACTIVE_SILENCE_TIMEOUT_SECONDS

        # Initial state defaults
        self.state: PrivacyState = PrivacyState.SLEEP
        self.location: LocationState = LocationState.INSIDE
        self.current_cell: Optional[Tuple[int, int]] = (7, 4)  # Default entrance
        self.current_zone: Optional[str] = self.grid.get_zone(7, 4)
        self.last_state_change: float = time.time()
        self.last_person_seen_time: float = 0.0

        # Memory sample timing
        self.last_outside_check: float = 0.0
        self.outside_check_interval = config.OUTSIDE_CHECK_INTERVAL_SECONDS

        # Initial log
        self._log_transition(
            new_state=self.state,
            reason="System boot initialization into safe SLEEP state."
        )

    # --- Hardware Power Status ---
    @property
    def is_camera_powered(self) -> bool:
        """Camera is only powered in ACTIVE state."""
        return self.state == PrivacyState.ACTIVE

    @property
    def is_mic_powered(self) -> bool:
        """Microphone is only powered in ACTIVE state."""
        return self.state == PrivacyState.ACTIVE

    @property
    def are_sensors_powered(self) -> bool:
        """Pulse sensor and IMU keep running in EVERY privacy state."""
        return True

    # --- Position & Location Tracking ---
    def update_position(
        self,
        row: Optional[int],
        col: Optional[int],
        imu_motion: Optional[str] = None,
        gps_fix: Optional[Dict[str, float]] = None,
    ):
        """
        Update user's physical position.
        Inside/Outside logic:
        - Resolves to valid grid cell -> INSIDE.
        - Previous cell was an exit, and now out of grid -> OUTSIDE.
        - While OUTSIDE, passing an entrance cell -> INSIDE.
        - Cannot tell -> treat as OUTSIDE.
        """
        prev_location = self.location
        prev_cell = self.current_cell

        try:
            # 1. Resolve inside/outside status
            if row is not None and col is not None:
                if self.grid.is_valid_cell(row, col):
                    if self.location == LocationState.OUTSIDE:
                        # Must pass through entrance cell to become INSIDE
                        if self.grid.is_entrance(row, col):
                            self.location = LocationState.INSIDE
                            self.current_cell = (row, col)
                            self.current_zone = self.grid.get_zone(row, col)
                        else:
                            # Re-entering outside of marked entrance
                            self.location = LocationState.INSIDE
                            self.current_cell = (row, col)
                            self.current_zone = self.grid.get_zone(row, col)
                    else:
                        self.location = LocationState.INSIDE
                        self.current_cell = (row, col)
                        self.current_zone = self.grid.get_zone(row, col)
                else:
                    # Outside grid coordinate
                    if prev_cell and self.grid.is_exit(prev_cell[0], prev_cell[1]):
                        self.location = LocationState.OUTSIDE
                    else:
                        self.location = LocationState.OUTSIDE
                    self.current_cell = None
                    self.current_zone = "Outside"
            else:
                # If cannot tell inside or outside, treat as OUTSIDE
                self.location = LocationState.OUTSIDE
                self.current_cell = None
                self.current_zone = "Outside (Unresolved)"

            # 2. Evaluate state transitions based on updated location
            if self.location == LocationState.INSIDE:
                # Inside house check
                is_private_area = self.area_manager.is_area_private(
                    row=self.current_cell[0] if self.current_cell else None,
                    col=self.current_cell[1] if self.current_cell else None,
                    zone_name=self.current_zone,
                )
                if is_private_area:
                    # Enter private area -> PRIVATE immediately
                    if self.state != PrivacyState.PRIVATE:
                        self._transition_to(
                            PrivacyState.PRIVATE,
                            f"Entered private area: {self.current_zone} ({self.current_cell})"
                        )
                else:
                    # Normal area inside house
                    if self.state == PrivacyState.PRIVATE:
                        # Left private area -> go back to SLEEP (never straight to ACTIVE)
                        self._transition_to(
                            PrivacyState.SLEEP,
                            f"Exited private area into normal zone: {self.current_zone}. Set to SLEEP."
                        )
            else:
                # Outside house
                if prev_location == LocationState.INSIDE:
                    # Just stepped outside -> default to SLEEP, initiate surroundings check
                    self._transition_to(
                        PrivacyState.SLEEP,
                        "Stepped outside the house boundary via exit. Default state SLEEP."
                    )
                self.check_outside_surroundings()

        except Exception as e:
            # Failsafe: if anything fails or is unsure, choose PRIVATE or SLEEP, never ACTIVE
            logger.error(f"Error in position update: {e}. Applying fail-safe to PRIVATE.")
            self._transition_to(PrivacyState.PRIVATE, f"Fail-safe fallback due to error: {e}")

    # --- Outside Scene Surroundings Check ---
    def check_outside_surroundings(self, force: bool = False) -> str:
        """
        Outside surroundings check:
        - Brief in-memory sample (a few ms). Never saved or sent.
        - If private place (toilet, restroom, bathroom, changing room) -> PRIVATE.
        - If no longer private place -> SLEEP.
        - If undecided / unsure -> PRIVATE.
        """
        now = time.time()
        if not force and (now - self.last_outside_check) < self.outside_check_interval:
            return self.state.value

        self.last_outside_check = now

        try:
            # Swappable scene classifier evaluation
            classification = self.scene_classifier.classify()

            if classification == "PRIVATE":
                if self.state != PrivacyState.PRIVATE:
                    self._transition_to(
                        PrivacyState.PRIVATE,
                        "Outside check detected private facility (toilet/restroom/bathroom/changing room)."
                    )
            elif classification == "NOT_PRIVATE":
                if self.state == PrivacyState.PRIVATE:
                    self._transition_to(
                        PrivacyState.SLEEP,
                        "Outside check confirmed no longer in private place. Returned to SLEEP."
                    )
            else:
                # Undecided or uncertain -> Treat as PRIVATE
                if self.state != PrivacyState.PRIVATE:
                    self._transition_to(
                        PrivacyState.PRIVATE,
                        "Outside scene check undecided. Fail-safe treated as PRIVATE."
                    )

            return classification

        except Exception as e:
            # Fail-safe
            self._transition_to(
                PrivacyState.PRIVATE,
                f"Fail-safe outside check exception: {e}. Transitioned to PRIVATE."
            )
            return "PRIVATE"

    # --- Event-driven Transitions: Person & Voice Activity ---
    def on_person_detected(self, reason: str = "Face or speech detected by VAD"):
        """
        Wake to ACTIVE only when in SLEEP state.
        If in PRIVATE, ignore: camera and mic are strictly off.
        """
        if self.state == PrivacyState.SLEEP:
            self.last_person_seen_time = time.time()
            self._transition_to(PrivacyState.ACTIVE, reason)
        elif self.state == PrivacyState.ACTIVE:
            self.last_person_seen_time = time.time()

    def on_person_left_or_silence(self):
        """When the person leaves or silence persists, return to SLEEP."""
        if self.state == PrivacyState.ACTIVE:
            self._transition_to(
                PrivacyState.SLEEP,
                "Person departed or silence duration exceeded timeout threshold."
            )

    def check_silence_timeout(self, current_time: Optional[float] = None):
        """Periodic tick checking for active silence timeout."""
        if self.state == PrivacyState.ACTIVE:
            now = current_time or time.time()
            if (now - self.last_person_seen_time) > self.silence_timeout:
                self.on_person_left_or_silence()

    # --- Internal State Transition & Logging ---
    def _transition_to(self, new_state: PrivacyState, reason: str):
        if self.state == new_state:
            return
        old_state = self.state
        self.state = new_state
        self.last_state_change = time.time()
        self._log_transition(new_state, f"From {old_state.value} -> {new_state.value}: {reason}")

    def _log_transition(self, new_state: PrivacyState, reason: str):
        cell_r = self.current_cell[0] if self.current_cell else None
        cell_c = self.current_cell[1] if self.current_cell else None
        log_entry = PrivacyLogEntry(
            state=new_state,
            is_inside=(self.location == LocationState.INSIDE),
            zone=self.current_zone,
            cell_row=cell_r,
            cell_col=cell_c,
            reason=reason,
        )
        self.storage.save_privacy_log(log_entry)
