"""
Tests for Step 5: Android Background App & Mobile Companion
- Whisper STT offline transcription and immediate audio purge
- Lightweight LLM conversation summarizer & importance scoring
- Selective saving above threshold (names, dates, times, medicine, appointments)
- Skipping casual talk
- Offline TTS reminder generation and daily summary output
"""

from pathlib import Path
from device.storage import SecureStorage
from device.models import Reminder
from mobile.mobile_agent import (
    WhisperSTTEngine,
    ConversationSummarizer,
    OfflineTTS,
    MobileCompanionApp,
)


def test_whisper_stt_purges_audio():
    stt = WhisperSTTEngine()
    audio_buffer = bytearray(b"RAW_AUDIO_STREAM_SAMPLES_CONFIDENTIAL_PCM_BYTES")
    assert len(audio_buffer) > 0

    transcript = stt.transcribe_and_purge(
        audio_buffer,
        simulated_transcript="Remember to take your medicine tomorrow at 8 AM."
    )
    assert "medicine" in transcript
    # Audio buffer is zeroed out for privacy
    assert all(b == 0 for b in audio_buffer)


def test_llm_importance_scoring_and_skipping_casual_talk():
    summarizer = ConversationSummarizer(importance_threshold=0.60)

    # 1. Casual talk -> Low score, should NOT be marked important
    casual_text = "Good morning! The weather is very nice today. Did you sleep well?"
    casual_res = summarizer.score_and_extract(casual_text)
    assert casual_res["importance_score"] < 0.60
    assert casual_res["is_important"] is False

    # 2. Critical conversation with appointment, medicine, and date/time -> High score
    important_text = (
        "Grandpa, remember tomorrow at 10 AM you have a doctor appointment with Dr. Sharma. "
        "Take your blood pressure medicine before leaving."
    )
    imp_res = summarizer.score_and_extract(important_text)
    assert imp_res["importance_score"] >= 0.60
    assert imp_res["is_important"] is True
    assert "tomorrow" in imp_res["entities"]["time_references"] or "10 am" in imp_res["entities"]["time_references"]
    assert "medicine" in imp_res["entities"]["keywords"]
    assert "appointment" in imp_res["entities"]["keywords"]


def test_mobile_companion_note_saving_pipeline(tmp_path: Path):
    db_file = tmp_path / "mobile_local.db"
    storage = SecureStorage(db_path=db_file)
    mobile_app = MobileCompanionApp(storage=storage)

    # Processing casual talk
    res_casual = mobile_app.process_audio_segment(
        audio_data=bytearray(b"casual"),
        person_id="p_01",
        person_label="Neighbor Bob",
        simulated_transcript="Good afternoon Bob! Nice flowers in your garden."
    )
    assert res_casual["saved"] is False
    assert res_casual["status"] == "skipped_casual_talk"
    # Verify no notes were saved to DB
    assert len(storage.get_notes()) == 0

    # Processing critical conversation
    res_imp = mobile_app.process_audio_segment(
        audio_data=bytearray(b"critical"),
        person_id="p_ananya",
        person_label="Ananya",
        simulated_transcript="Grandpa, remember your cardiology appointment on Friday morning and take your heart pills."
    )
    assert res_imp["saved"] is True
    assert res_imp["status"] == "saved"

    # Verify Note was saved and linked to Ananya
    notes = storage.get_notes()
    assert len(notes) == 1
    assert "Ananya" in notes[0].content
    assert notes[0].person_id == "p_ananya"


def test_offline_tts_speech_generation():
    tts = OfflineTTS()

    # 1. Reminder speech
    rem = Reminder(
        title="Thyroid Tablet",
        description="Take 1 tablet on empty stomach",
        scheduled_time="07:00",
        category="medication"
    )
    rem_text = tts.speak_reminder(rem)
    assert "Thyroid Tablet" in rem_text
    assert "empty stomach" in rem_text

    # 2. Person encounter speech
    encounter_text = tts.speak_person_encounter(
        person_label="Ananya",
        relationship="granddaughter",
        last_topic="her college exam"
    )
    assert "This is your granddaughter, Ananya." in encounter_text
    assert "her college exam" in encounter_text

    # 3. Daily summary speech
    summary_text = tts.generate_daily_summary(
        people_met=["Ananya", "Nurse Priya"],
        reminders_remaining=[rem],
        important_notes=["Doctor visit at 3pm"]
    )
    assert "Today you met Ananya, Nurse Priya." in summary_text
    assert "Thyroid Tablet at 07:00" in summary_text
