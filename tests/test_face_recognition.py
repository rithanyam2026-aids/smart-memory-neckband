"""
Unit tests for Step 2: Face recognition, embedding averaging, unknown-to-familiar promotion,
and doubtful match privacy guard.
"""

import math
from pathlib import Path
from device.models import Person, PersonStatus
from device.storage import SecureStorage
from device.face_recognition import (
    FaceRecognitionEngine,
    FaceEmbedder,
    cosine_similarity,
    average_embeddings,
    update_running_average,
    normalize_vector,
)


def test_cosine_similarity():
    # Identical vectors -> 1.0
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    assert math.isclose(cosine_similarity(v1, v2), 1.0, rel_tol=1e-5)

    # Orthogonal vectors -> 0.0
    v3 = [0.0, 1.0, 0.0]
    assert math.isclose(cosine_similarity(v1, v3), 0.0, abs_tol=1e-5)

    # Opposite vectors -> -1.0
    v4 = [-1.0, 0.0, 0.0]
    assert math.isclose(cosine_similarity(v1, v4), -1.0, rel_tol=1e-5)


def test_embedding_averaging():
    e1 = [1.0, 0.0]
    e2 = [0.0, 1.0]
    avg = average_embeddings([e1, e2])
    expected_val = 1.0 / math.sqrt(2)
    assert math.isclose(avg[0], expected_val, rel_tol=1e-5)
    assert math.isclose(avg[1], expected_val, rel_tol=1e-5)

    # Running average update
    current_avg = [1.0, 0.0]
    updated = update_running_average(current_avg, current_count=1, new_embedding=[0.0, 1.0])
    assert math.isclose(updated[0], expected_val, rel_tol=1e-5)


def test_face_image_deleted_immediately():
    embedder = FaceEmbedder(embedding_dim=16)
    fake_image_bytes = bytearray(b"RAW_CAMERA_PIXELS_CONFIDENTIAL_12345")
    assert len(fake_image_bytes) > 0

    emb = embedder.extract_embedding_and_delete_image(fake_image_bytes, seed_key="ananya_test")
    assert len(emb) == 16
    # Verify image bytearray was zeroed out for privacy
    assert all(b == 0 for b in fake_image_bytes)


def test_unknown_to_familiar_progression_and_doubtful(tmp_path: Path):
    db_file = tmp_path / "test_neckband.db"
    storage = SecureStorage(db_path=db_file)
    engine = FaceRecognitionEngine(
        storage=storage,
        similarity_threshold=0.70,
        doubtful_threshold=0.50,
        familiar_threshold=3,
    )

    # Meeting 1: Brand new face -> Unknown #1 (stranger)
    emb_person_a = normalize_vector([0.8, 0.2, 0.1, 0.0] + [0.0] * 124)
    res1 = engine.identify_or_register(emb_person_a, zone="Living Room")
    assert res1["match"] is False
    assert res1["person"].label == "Unknown #1"
    assert res1["person"].status == PersonStatus.STRANGER
    assert res1["person"].visit_count == 1
    assert "I'm not sure" in res1["announcement"]

    # Meeting 2: Same person with slight angle/lighting difference (similarity > 0.70)
    emb_person_a_variant = normalize_vector([0.78, 0.22, 0.12, 0.0] + [0.0] * 124)
    res2 = engine.identify_or_register(emb_person_a_variant, zone="Kitchen")
    assert res2["match"] is True
    assert res2["person"].label == "Unknown #1"
    assert res2["person"].visit_count == 2
    assert res2["person"].status == PersonStatus.STRANGER  # Not yet familiar (threshold is 3)

    # Meeting 3: Reaches familiar threshold -> automatically becomes 'familiar'
    emb_person_a_variant3 = normalize_vector([0.79, 0.21, 0.11, 0.0] + [0.0] * 124)
    res3 = engine.identify_or_register(emb_person_a_variant3, zone="Dining Area")
    assert res3["match"] is True
    assert res3["person"].visit_count == 3
    assert res3["person"].status == PersonStatus.FAMILIAR  # Successfully promoted!

    # Meeting 4: Caregiver customises name & relationship in dashboard
    res3["person"].label = "Ananya"
    res3["person"].relationship = "granddaughter"
    storage.save_person(res3["person"])

    res4 = engine.identify_or_register(emb_person_a, zone="Living Room")
    assert res4["match"] is True
    assert "granddaughter, Ananya" in res4["announcement"]

    # Test Doubtful Match: similarity between 0.50 and 0.70
    # Vector partially aligned with person A
    doubtful_emb = normalize_vector([0.45, 0.45, 0.45, 0.45] + [0.0] * 124)
    sim = cosine_similarity(doubtful_emb, res4["person"].embedding)
    assert 0.50 <= sim < 0.70

    res_doubtful = engine.identify_or_register(doubtful_emb)
    assert res_doubtful["match"] is False
    assert res_doubtful["doubtful"] is True
    assert res_doubtful["announcement"] == "I'm not sure who this is."
    assert res_doubtful["sighting"].is_doubtful is True
