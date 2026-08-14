"""FastAPI dependencies."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Cookie, Depends, HTTPException, Request, status

from app.auth.session import load_session_token
from app.config import settings
from app.db.app_db import AppDB
from app.repositories.digikam_repo import DigikamRepository
from app.services.path_resolver import PathResolver
from app.services.thumbnail import ThumbnailService


# These are set at startup in main.py
_app_db: Optional[AppDB] = None
_digikam: Optional[DigikamRepository] = None
_resolver: Optional[PathResolver] = None
_thumbs: Optional[ThumbnailService] = None


def set_globals(
    app_db: AppDB,
    digikam: DigikamRepository,
    resolver: PathResolver,
    thumbs: ThumbnailService,
) -> None:
    global _app_db, _digikam, _resolver, _thumbs
    _app_db = app_db
    _digikam = digikam
    _resolver = resolver
    _thumbs = thumbs


def get_app_db() -> AppDB:
    if _app_db is None:
        raise RuntimeError("AppDB not initialised")
    return _app_db


def get_digikam() -> DigikamRepository:
    if _digikam is None:
        raise RuntimeError("DigikamRepository not initialised")
    return _digikam


def get_resolver() -> PathResolver:
    if _resolver is None:
        raise RuntimeError("PathResolver not initialised")
    return _resolver


def get_thumbs() -> ThumbnailService:
    if _thumbs is None:
        raise RuntimeError("ThumbnailService not initialised")
    return _thumbs


def get_current_user(
    request: Request,
    session: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
) -> dict[str, Any]:
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    user = load_session_token(session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )
    return user


def get_optional_user(
    session: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
) -> Optional[dict[str, Any]]:
    if not session:
        return None
    return load_session_token(session)
