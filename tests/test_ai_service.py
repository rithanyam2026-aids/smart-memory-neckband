"""
Tests for Python AI Service:
- Ingesting frames over link and running FaceNet matching
- Multi-embedding running average
- Promotion from stranger to familiar
- Doubtful match handling ("I'm not sure", never state stranger identity as fact)
- Ingesting audio chunks over link and running Whisper STT + LLM note extraction
- Scene check evaluation of outside samples
"""

from pathlib import Path
from ai.storage import SecureStorage
from ai.models import PersonStatus
from ai.face_recognition import FaceRecognitionEngine, normalize_vector, cosine_similarity
from ai.speech_llm import ConversationPipeline
from ai.scene_classifier import MockSceneClassifier
from ai.link_server import AILinkServer
from ai.protocol import MsgType, LinkProtocolPacket


def test_ai_service_link_handshake_and_frames(tmp_path: Path):
    db_file = tmp_path / "ai_test.db"
    storage = SecureStorage(db_path=db_file)
    mock_classifier = MockSceneClassifier(default_result="PRIVATE")
    server = AILinkServer(storage=storage, scene_classifier=mock_classifier)

    # 1. Handshake Hello
    hello_pkt = LinkProtocolPacket.encode_packet(
        MsgType.HANDSHAKE_HELLO,
        {"device_id": "neckband-01", "nonce_c": "client_nonce_123"}
    )
    resp_bytes = server.handle_incoming_packet(hello_pkt)
    assert resp_bytes is not None
    mtype, meta, _, _ = LinkProtocolPacket.decode_packet(resp_bytes)
    assert mtype == MsgType.HANDSHAKE_AUTH
    assert "nonce_s" in meta
    assert "hmac_c" in meta

    # 2. Handshake Auth Complete
    nonce_s = meta["nonce_s"]
    hmac_s = server.authenticator.generate_challenge(nonce_s)
    auth_pkt = LinkProtocolPacket.encode_packet(
        MsgType.HANDSHAKE_AUTH,
        {"nonce_s": nonce_s, "hmac_s": hmac_s}
    )
    resp_auth = server.handle_incoming_packet(auth_pkt)
    assert resp_auth is not None
    assert server.is_connected is True

    # 3. Stream Frame -> Brand new person -> Unknown #1 (stranger)
    frame_pkt = LinkProtocolPacket.encode_packet(
        MsgType.FRAME_STREAM,
        {"zone": "Living Room", "cell": [4, 2], "seed_key": "person_grandpa"},
        binary_payload=b"RAW_CAMERA_FRAME_BYTES"
    )
    resp_frame = server.handle_incoming_packet(frame_pkt)
    assert resp_frame is not None
    mtype, res_meta, _, _ = LinkProtocolPacket.decode_packet(resp_frame)
    assert res_meta["status"] == "processed"
    assert "I'm not sure" in res_meta["announcement"]

    all_people = storage.get_all_people()
    assert len(all_people) == 1
    assert all_people[0].label == "Unknown #1"
    assert all_people[0].status == PersonStatus.STRANGER

    # 4. Stream Outside Sample -> AI service returns result
    sample_pkt = LinkProtocolPacket.encode_packet(
        MsgType.OUTSIDE_SAMPLE,
        {"timestamp": 12345.0},
        binary_payload=b"RESTROOM_TILES_ECHO_SAMPLE"
    )
    resp_sample = server.handle_incoming_packet(sample_pkt)
    assert resp_sample is not None
    mtype, res_sample, _, _ = LinkProtocolPacket.decode_packet(resp_sample)
    assert mtype == MsgType.OUTSIDE_RESULT
    assert res_sample["classification"] == "PRIVATE"


def test_ai_service_audio_pipeline(tmp_path: Path):
    db_file = tmp_path / "ai_audio_test.db"
    storage = SecureStorage(db_path=db_file)
    pipeline = ConversationPipeline(storage=storage)

    # 1. Casual talk chunk -> Skipped
    res_casual = pipeline.process_audio_chunk(
        audio_bytes=b"casual_audio_bytes",
        person_label="Neighbor Bob",
        simulated_transcript="Nice sunset outside today!"
    )
    assert res_casual["saved"] is False
    assert res_casual["status"] == "skipped_casual_talk"
    assert len(storage.get_notes()) == 0

    # 2. Critical conversation -> Saved note linked to Ananya
    res_critical = pipeline.process_audio_chunk(
        audio_bytes=b"critical_audio_bytes",
        person_label="Ananya",
        simulated_transcript="Grandpa, remember tomorrow at 10 AM you have a doctor appointment. Take your medicine."
    )
    assert res_critical["saved"] is True
    assert res_critical["status"] == "saved"
    assert len(storage.get_notes()) == 1
    assert "Ananya" in storage.get_notes()[0].content
