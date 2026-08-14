"""Default map link templates and helpers.

Templates use placeholders:
  {lat}  {lon}  {lat:.5f} style is NOT supported — use plain {lat}/{lon}
  Optional: {zoom}

Stored in app DB config key: map_link_templates (JSON array).
"""

from __future__ import annotations

import json
from typing import Any

DEFAULT_MAP_LINK_TEMPLATES: list[dict[str, str]] = [
    {
        "id": "google",
        "name": "Google Maps",
        "url": "https://www.google.com/maps?q={lat},{lon}",
    },
    {
        "id": "google_street",
        "name": "Google Street View",
        "url": "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}",
    },
    {
        "id": "osm",
        "name": "OpenStreetMap",
        "url": "https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map={zoom}/{lat}/{lon}",
    },
    {
        "id": "bing",
        "name": "Bing Maps",
        "url": "https://www.bing.com/maps?cp={lat}~{lon}&lvl={zoom}",
    },
    {
        "id": "apple",
        "name": "Apple Maps",
        "url": "https://maps.apple.com/?ll={lat},{lon}&q={lat},{lon}",
    },
]

CONFIG_KEY = "map_link_templates"
DEFAULT_ZOOM = "15"


def default_templates_json() -> str:
    return json.dumps(DEFAULT_MAP_LINK_TEMPLATES, ensure_ascii=False, indent=2)


def parse_templates(raw: str | None) -> list[dict[str, str]]:
    if not raw:
        return list(DEFAULT_MAP_LINK_TEMPLATES)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return list(DEFAULT_MAP_LINK_TEMPLATES)
    if not isinstance(data, list):
        return list(DEFAULT_MAP_LINK_TEMPLATES)
    out: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").strip()
        if not name or not url or "{lat}" not in url or "{lon}" not in url:
            continue
        out.append(
            {
                "id": str(item.get("id") or name.lower().replace(" ", "_")),
                "name": name,
                "url": url,
            }
        )
    return out or list(DEFAULT_MAP_LINK_TEMPLATES)


def ensure_map_templates(app_db: Any) -> list[dict[str, str]]:
    """Load templates from app DB; seed defaults if missing."""
    raw = app_db.get_config(CONFIG_KEY)
    if not raw:
        app_db.set_config(CONFIG_KEY, default_templates_json())
        return list(DEFAULT_MAP_LINK_TEMPLATES)
    return parse_templates(raw)
