"""Local-first operator authentication and authorization for FloodSense AI.

Guards municipal verification, triage decisions, and emergency dispatches
against unauthorized access using a secure local operator key.
"""
from __future__ import annotations

import hmac
import os
from fastapi import Header, HTTPException, status

DEFAULT_OPERATOR_KEY = "bbmp-operator-secret-2026"
OPERATOR_ENV_VAR = "OPERATOR_API_KEY"


def get_configured_operator_key() -> str:
    """Retrieves configured operator secret key from environment or local default."""
    return os.environ.get(OPERATOR_ENV_VAR, DEFAULT_OPERATOR_KEY)


def verify_operator_access(
    x_operator_key: str | None = Header(default=None, alias="X-Operator-Key")
) -> str:
    """FastAPI security dependency ensuring callers possess valid operator credentials."""
    expected_key = get_configured_operator_key()

    if not x_operator_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization required: Missing X-Operator-Key header. Only municipal operators can perform verification.",
        )

    # Constant time comparison to prevent timing attacks
    if not hmac.compare_digest(x_operator_key.encode("utf-8"), expected_key.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Forbidden: Invalid operator credentials provided.",
        )

    return "verified_operator"

