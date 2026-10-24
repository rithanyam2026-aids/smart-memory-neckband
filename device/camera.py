"""
Hardware Camera Module for Smart Memory Neckband.
Features:
- Camera hardware interface with mock mode for laptop testing
- Captures frames ONLY when privacy state is ACTIVE
- Strictly disabled in PRIVATE and SLEEP states
- Discards raw frame buffer immediately after embedding extraction
"""

from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import Optional, Any
from device.models import PrivacyState

logger = logging.getLogger("Camera")


class CameraInterface(ABC):
    @abstractmethod
    def capture_frame(self, current_privacy_state: PrivacyState) -> Optional[bytearray]:
        """Captures a frame if and only if privacy state permits."""
        pass


class MockCamera(CameraInterface):
    def __init__(self, simulated_face_key: Optional[str] = "granddaughter_ananya"):
        self.simulated_face_key = simulated_face_key

    def set_simulated_face(self, key: Optional[str]):
        self.simulated_face_key = key

    def capture_frame(self, current_privacy_state: PrivacyState) -> Optional[bytearray]:
        if current_privacy_state != PrivacyState.ACTIVE:
            logger.debug(f"Camera capture blocked in {current_privacy_state.value} state.")
            return None

        # Return mock raw image bytearray that will be zeroed out upon extraction
        mock_data = bytearray(f"CAMERA_PIXELS_FOR_{self.simulated_face_key}".encode("utf-8"))
        return mock_data
