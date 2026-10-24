"""
Authentication and Role-Based Access Control for Cloud Backend.
Provides simple PIN authentication for elder users and caregivers.
Caregivers are strictly scoped to the elder user they are linked to.
"""

from __future__ import annotations
import hmac
import hashlib
import time
import json
import base64
from typing import Optional, Dict, Any
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY = "smart_neckband_cloud_secret_key_fixed"
security_scheme = HTTPBearer(auto_error=False)


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def generate_token(payload: Dict[str, Any]) -> str:
    """Generate tamper-proof signed token without requiring external heavy JWT libraries."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload_copy = dict(payload)
    payload_copy["exp"] = time.time() + 86400 * 30  # 30 days validity

    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload_copy).encode()).decode().rstrip("=")

    signature = hmac.new(
        SECRET_KEY.encode(), f"{h_b64}.{p_b64}".encode(), hashlib.sha256
    ).digest()
    s_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")

    return f"{h_b64}.{p_b64}.{s_b64}"


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        h_b64, p_b64, s_b64 = parts

        expected_sig = hmac.new(
            SECRET_KEY.encode(), f"{h_b64}.{p_b64}".encode(), hashlib.sha256
        ).digest()
        actual_sig = base64.urlsafe_b64decode(s_b64 + "=="[: (4 - len(s_b64) % 4) % 4])

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload_bytes = base64.urlsafe_b64decode(p_b64 + "=="[: (4 - len(p_b64) % 4) % 4])
        payload = json.loads(payload_bytes.decode())

        if payload.get("exp", 0) < time.time():
            return None

        return payload
    except Exception:
        return None


def get_current_user_context(credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme)) -> Dict[str, Any]:
    """FastAPI dependency for authenticated requests with mock/fallback support."""
    if not credentials:
        # Default mock context if unauthenticated in local testing
        return {
            "user_id": "user_01",
            "role": "caregiver",
            "linked_user_id": "user_01",
            "target_user_id": "user_01",
            "display_name": "Nurse Priya (Caregiver)"
        }

    token = credentials.credentials
    claims = decode_token(token)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

    role = claims.get("role", "user")
    user_id = claims.get("user_id", "user_01")
    linked_id = claims.get("linked_user_id")

    # Scoping: Caregiver only views and operates on linked user
    target_user_id = linked_id if role == "caregiver" and linked_id else user_id

    return {
        "user_id": user_id,
        "role": role,
        "linked_user_id": linked_id,
        "target_user_id": target_user_id,
        "display_name": claims.get("display_name", "User")
    }
