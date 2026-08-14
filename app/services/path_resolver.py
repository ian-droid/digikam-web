"""Resolve DigiKam image IDs to absolute filesystem paths (read-only)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.db.app_db import AppDB
from app.repositories.digikam_repo import DigikamRepository


class PathResolver:
    def __init__(self, app_db: AppDB, digikam: DigikamRepository):
        self.app_db = app_db
        self.digikam = digikam
        self._root_cache: dict[int, Path] = {}
        self._load_roots()

    def _load_roots(self) -> None:
        for root in self.app_db.get_album_roots():
            self._root_cache[root["digikam_id"]] = Path(root["specific_path"])

    def refresh(self) -> None:
        self._root_cache.clear()
        self._load_roots()

    def resolve_image(self, image_id: int) -> Optional[Path]:
        """
        Return absolute Path to the media file, or None if it cannot be resolved
        or does not exist / is not a file.
        """
        img = self.digikam.get_image(image_id)
        if not img:
            return None

        root_id = img.get("albumRoot")
        if root_id is None:
            return None

        root_path = self._root_cache.get(root_id)
        if root_path is None:
            # try reloading once
            self.refresh()
            root_path = self._root_cache.get(root_id)
            if root_path is None:
                return None

        album_rel = (img.get("album_relative_path") or "").lstrip("/")
        name = img.get("name") or ""
        if not name:
            return None

        # DigiKam relativePath for the root album is usually "/"
        if album_rel in ("", "/"):
            full = root_path / name
        else:
            full = root_path / album_rel / name

        try:
            full = full.resolve(strict=False)
        except Exception:
            return None

        # Safety: must stay under the declared root
        try:
            full.relative_to(root_path.resolve())
        except ValueError:
            return None

        if full.is_file():
            return full
        return None
