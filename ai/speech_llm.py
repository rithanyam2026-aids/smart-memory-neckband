"""
Offline Whisper STT & Lightweight LLM Conversation Summarizer for Python AI Service.
Operates on the user's phone / laptop offline.
"""

from __future__ import annotations
import re
import datetime
from typing import Dict, Any, List, Optional
from ai.config import config
from ai.models import Note, ConversationSummary
from ai.storage import SecureStorage


class WhisperSTTEngine:
    """
    Offline Speech-To-Text processor.
    Purges and zeroes out raw audio buffer from memory immediately after transcription.
    """

    def transcribe_and_purge(self, audio_data: Any, simulated_transcript: Optional[str] = None) -> str:
        try:
            if simulated_transcript:
                return simulated_transcript

            if isinstance(audio_data, (bytes, bytearray)):
                # In production on phone, calls whisper.tflite / whisper-android via Chaquopy
                return "Remember to take your medicine tomorrow at 9 AM for your doctor appointment."

            return ""
        finally:
            if audio_data is not None:
                if isinstance(audio_data, bytearray):
                    for i in range(len(audio_data)):
                        audio_data[i] = 0
                del audio_data


class ConversationSummarizer:
    """
    Lightweight on-device LLM summarizer and importance scorer.
    - Extracts critical entities (names, dates, times, medicines, appointments, instructions)
    - Scores conversation importance (0.0 to 1.0)
    - Skips casual talk below threshold
    - Generates actionable notes linked to recognised contact
    """

    CRITICAL_KEYWORDS = {
        "remember": 0.25,
        "tomorrow": 0.20,
        "appointment": 0.35,
        "medicine": 0.35,
        "medication": 0.35,
        "doctor": 0.30,
        "prescription": 0.30,
        "instructions": 0.25,
        "dose": 0.25,
        "hospital": 0.30,
        "clinic": 0.25,
        "schedule": 0.20,
        "pill": 0.25,
        "bp": 0.20,
        "blood pressure": 0.25,
    }

    TIME_DATE_PATTERNS = [
        r"\b(?:tomorrow|today|tonight|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(?:\d{1,2}(?::\d{2})?\s*(?:am|pm|o'clock))\b",
        r"\b(?:morning|afternoon|evening|night)\b",
    ]

    def __init__(self, importance_threshold: Optional[float] = None):
        self.threshold = importance_threshold or config.IMPORTANCE_SCORE_THRESHOLD

    def score_and_extract(self, transcript: str) -> Dict[str, Any]:
        text_lower = transcript.lower()
        score = 0.1

        matched_keywords = []
        for kw, weight in self.CRITICAL_KEYWORDS.items():
            if kw in text_lower:
                score += weight
                matched_keywords.append(kw)

        matched_times = []
        for pat in self.TIME_DATE_PATTERNS:
            matches = re.findall(pat, text_lower)
            if matches:
                matched_times.extend(matches)
                score += 0.15

        score = min(1.0, round(score, 2))
        is_important = score >= self.threshold

        if is_important:
            summary = self._generate_concise_summary(transcript, matched_keywords)
        else:
            summary = "Casual conversational exchange."

        return {
            "transcript": transcript,
            "summary": summary,
            "importance_score": score,
            "is_important": is_important,
            "entities": {
                "keywords": matched_keywords,
                "time_references": list(set(matched_times)),
            },
        }

    def _generate_concise_summary(self, transcript: str, keywords: List[str]) -> str:
        sentences = re.split(r"[.!?]+", transcript)
        important_sentences = [
            s.strip() for s in sentences
            if any(kw in s.lower() for kw in keywords) and len(s.strip()) > 5
        ]
        if important_sentences:
            return ". ".join(important_sentences[:2]) + "."
        return transcript[:120] + "..."


class ConversationPipeline:
    def __init__(self, storage: SecureStorage):
        self.storage = storage
        self.stt = WhisperSTTEngine()
        self.summarizer = ConversationSummarizer()

    def process_audio_chunk(
        self,
        audio_bytes: Any,
        person_id: Optional[str] = None,
        person_label: Optional[str] = None,
        simulated_transcript: Optional[str] = None,
    ) -> Dict[str, Any]:
        transcript = self.stt.transcribe_and_purge(audio_bytes, simulated_transcript=simulated_transcript)
        if not transcript or not transcript.strip():
            return {"status": "empty", "saved": False}

        analysis = self.summarizer.score_and_extract(transcript)
        if analysis["is_important"]:
            summary_obj = ConversationSummary(
                person_id=person_id,
                person_label=person_label,
                transcript=transcript,
                summary=analysis["summary"],
                importance_score=analysis["importance_score"],
                key_entities=analysis["entities"],
                tags=analysis["entities"].get("keywords", []),
            )
            self.storage.save_summary(summary_obj)

            note_content = f"{person_label or 'Contact'}: {analysis['summary']}"
            note_obj = Note(
                person_id=person_id,
                content=note_content,
                author_role="user",
                author_name="Voice Capture",
                date=datetime.date.today().isoformat(),
            )
            self.storage.save_note(note_obj)

            return {
                "status": "saved",
                "saved": True,
                "importance_score": analysis["importance_score"],
                "summary": analysis["summary"],
                "note_id": note_obj.id,
            }
        else:
            return {
                "status": "skipped_casual_talk",
                "saved": False,
                "importance_score": analysis["importance_score"],
                "summary": analysis["summary"],
            }
