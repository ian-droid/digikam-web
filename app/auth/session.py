"""Simple signed cookie session handling."""

from __future__ import annotations

import json
from typing import Any, Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="digikam-web-session")


def create_session_token(user: dict[str, Any]) -> str:
    payload = {
        "uid": user["id"],
        "username": user["username"],
        "is_admin": user.get("is_admin", False),
    }
    return _serializer().dumps(payload)


def load_session_token(token: str) -> Optional[dict[str, Any]]:
    try:
        data = _serializer().loads(token, max_age=settings.session_max_age)
        return data
    except (BadSignature, SignatureExpired):
        return None
