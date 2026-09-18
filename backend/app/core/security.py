"""
Security utilities for IntelliRoads authentication gate.

Provides token generation and verification using standard library HMAC-SHA256,
and FastAPI dependencies to protect dashboard endpoints.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")
SECRET_KEY: str = os.getenv("SECRET_KEY", "intelliroads-secret-key-2026")
TOKEN_EXPIRE_SECONDS: int = 86400

bearer_scheme = HTTPBearer(auto_error=False)


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def create_access_token(username: str) -> str:
    """
    Generate a signed HMAC-SHA256 JWT access token for a given user.

    Encodes standard JWT header (HS256) and payload containing subject (`sub`),
    issued-at (`iat`), and expiration (`exp`) claims, signed with `SECRET_KEY`.

    Args:
        username: Subject identifier (username) to embed in token payload.

    Returns:
        str: Standard base64url-encoded JWT string formatted as `header.payload.signature`.
    """
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_EXPIRE_SECONDS,
    }

    header_b64 = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode an HMAC-SHA256 JWT access token.

    Validates formatting, verifies the signature against `SECRET_KEY` using constant-time
    comparison (`hmac.compare_digest`), and checks payload expiration (`exp`).

    Args:
        token: Base64url-encoded JWT string to verify.

    Returns:
        Optional[Dict[str, Any]]: Decoded payload dictionary if valid and non-expired, or `None` if invalid.
    """
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            return None

        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")

        expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
        expected_sig_b64 = _base64url_encode(expected_sig)

        if not hmac.compare_digest(sig_b64, expected_sig_b64):
            return None

        payload_bytes = base64.urlsafe_b64decode(payload_b64 + "=" * (4 - (len(payload_b64) % 4)))
        payload = json.loads(payload_bytes.decode("utf-8"))

        if time.time() > payload.get("exp", 0):
            return None

        return payload
    except Exception:
        return None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Dict[str, Any]:
    """
    FastAPI dependency to extract and authenticate current user from Bearer header.

    Args:
        credentials: Extracted HTTP Authorization Bearer credentials from request.

    Raises:
        HTTPException (401 Unauthorized): If credentials are missing, signature invalid, or expired.

    Returns:
        Dict[str, Any]: Dictionary containing authenticated user details (`{"username": ...}`).
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"username": payload["sub"]}


def verify_ws_token(token: Optional[str]) -> bool:
    """
    Validate a WebSocket connection authentication token passed via query string.

    Args:
        token: Access token string passed by WebSocket client.

    Returns:
        bool: `True` if token is valid and unexpired, `False` otherwise.
    """
    if not token:
        return False
    payload = verify_token(token)
    return payload is not None and "sub" in payload