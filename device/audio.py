"""
Hardware Audio & Voice Output Module for Smart Memory Neckband.
Features:
- Microphone capture with Voice Activity Detection (VAD)
- Respects privacy state: strictly inactive in PRIVATE and SLEEP (except for wake trigger)
- Voice output / TTS for person reminders and alerts
- Mock modes for all audio hardware
"""

from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from device.models import PrivacyState

logger = logging.getLogger("Audio")


class MicrophoneInterface(ABC):
    @abstractmethod
    def detect_voice_activity(self) -> bool:
        """Determines if human speech is present to decide when to wake."""
        pass

    @abstractmethod
    def capture_speech_audio(self, current_privacy_state: PrivacyState) -> Optional[bytearray]:
        """Captures audio stream for forwarding to phone STT."""
        pass


class MockMicrophone(MicrophoneInterface):
    def __init__(self, is_speech_active: bool = False):
        self.speech_active = is_speech_active

    def set_speech_active(self, active: bool):
        self.speech_active = active

    def detect_voice_activity(self) -> bool:
        return self.speech_active

    def capture_speech_audio(self, current_privacy_state: PrivacyState) -> Optional[bytearray]:
        if current_privacy_state != PrivacyState.ACTIVE:
            return None
        return bytearray(b"MOCK_PCM_SPEECH_STREAM_AUDIO_16KHZ")


class VoiceOutputInterface(ABC):
    @abstractmethod
    def speak(self, text: str):
        """Speak out loud to the senior user."""
        pass


class MockVoiceOutput(VoiceOutputInterface):
    def __init__(self):
        self.last_spoken_text: Optional[str] = None
        self.spoken_history: list[str] = []

    def speak(self, text: str):
        self.last_spoken_text = text
        self.spoken_history.append(text)
        logger.info(f"🔊 Neckband Speaker: '{text}'")
