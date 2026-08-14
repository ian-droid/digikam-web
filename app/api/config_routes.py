"""Read-only app config endpoints exposed to the web UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_app_db, get_current_user
from app.db.app_db import AppDB
from app.map_links import ensure_map_templates

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/map-links")
def get_map_links(
    user=Depends(get_current_user),
    app_db: AppDB = Depends(get_app_db),
):
    """Map website templates for building geo links on the client."""
    templates = ensure_map_templates(app_db)
    return {"templates": templates, "default_zoom": "15"}
