"""On-the-fly thumbnail generation from original media files (Pillow → WebP/JPEG)."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageOps

DEFAULT_SIZE = 320
QUALITY = 82


class ThumbnailService:
    def __init__(self, cache_dir: Optional[Path] = None, prefer_webp: bool = True):
        self.cache_dir = cache_dir
        self.prefer_webp = prefer_webp
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str, ext: str) -> Optional[Path]:
        if not self.cache_dir:
            return None
        return self.cache_dir / f"{key}.{ext}"

    def get_thumbnail(
        self,
        source: Path,
        size: int = DEFAULT_SIZE,
        fmt: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """
        Generate a thumbnail from the original file.
        Returns (bytes, media_type). Prefer WebP when supported.
        """
        if not source.is_file():
            raise FileNotFoundError(str(source))

        use_webp = (fmt or ("WEBP" if self.prefer_webp else "JPEG")).upper() == "WEBP"
        ext = "webp" if use_webp else "jpg"
        media_type = "image/webp" if use_webp else "image/jpeg"

        cache_key = hashlib.sha1(
            f"{source}:{source.stat().st_mtime_ns}:{source.stat().st_size}:{size}:{ext}".encode()
        ).hexdigest()
        cached = self._cache_path(cache_key, ext)
        if cached and cached.is_file():
            return cached.read_bytes(), media_type

        with Image.open(source) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((size, size), Image.Resampling.LANCZOS)
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")

            buf = BytesIO()
            if use_webp:
                im.save(buf, format="WEBP", quality=QUALITY, method=4)
            else:
                im.save(buf, format="JPEG", quality=QUALITY, optimize=True)
            data = buf.getvalue()

        if cached:
            try:
                cached.write_bytes(data)
            except OSError:
                pass

        return data, media_type
