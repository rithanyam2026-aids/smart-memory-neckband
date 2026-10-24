"""
Configuration for the Python AI Service (running on Phone via Chaquopy or Laptop).
"""

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class AIConfig:
    # Local Link with ESP32 Neckband
    LINK_HOST: str = os.getenv("LINK_HOST", "0.0.0.0")
    LINK_PORT: int = int(os.getenv("LINK_PORT", "8765"))
    LINK_PRESHARED_KEY: str = os.getenv("LINK_PRESHARED_KEY", "smart_memory_neckband_psk_shared_key_32b_fixed")
    LINK_HEARTBEAT_TIMEOUT_SEC: float = float(os.getenv("LINK_HEARTBEAT_TIMEOUT_SEC", "2.5"))

    # Security & Encryption
    AI_ENCRYPTION_KEY: str = os.getenv(
        "DEVICE_ENCRYPTION_KEY",
        "s3cr3t_K3y_Neckband_32_bytes_safe_aes_base64_demo="
    )
    DEVICE_ID: str = os.getenv("DEVICE_ID", "neckband-01")

    # Cloud & MQTT Endpoints
    CLOUD_API_URL: str = os.getenv("CLOUD_API_URL", "http://localhost:8000")
    MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "localhost")
    MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
    MQTT_TOPIC_ALERTS: str = os.getenv("MQTT_TOPIC_ALERTS", "smartneckband/device/alerts")
    MQTT_TOPIC_STATUS: str = os.getenv("MQTT_TOPIC_STATUS", "smartneckband/device/status")

    # Face Recognition Thresholds
    FACE_SIMILARITY_THRESHOLD: float = float(os.getenv("FACE_SIMILARITY_THRESHOLD", "0.68"))
    DOUBTFUL_SIMILARITY_THRESHOLD: float = float(os.getenv("DOUBTFUL_SIMILARITY_THRESHOLD", "0.52"))
    FAMILIAR_VISIT_THRESHOLD: int = int(os.getenv("FAMILIAR_VISIT_THRESHOLD", "3"))

    # Speech and LLM
    IMPORTANCE_SCORE_THRESHOLD: float = float(os.getenv("IMPORTANCE_SCORE_THRESHOLD", "0.60"))

    # Retention Durations (Days)
    STRANGER_RETENTION_DAYS: int = int(os.getenv("STRANGER_RETENTION_DAYS", "30"))
    NOTES_RETENTION_DAYS: int = int(os.getenv("NOTES_RETENTION_DAYS", "60"))

    # Database
    LOCAL_DB_PATH: Path = PROJECT_ROOT / "data" / "ai_local.db"
    BLUEPRINT_FILE: Path = PROJECT_ROOT / "data" / "house_grid.sample.json"


config = AIConfig()
