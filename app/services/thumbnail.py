"""On-the-fly thumbnail generation from original media files (Pillow → WebP/JPEG).

Unsupported types (video, etc.) get a generated placeholder instead of raising.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from typing import Optional, Set, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps

DEFAULT_SIZE = 320
QUALITY = 82

# Extensions we attempt to open with Pillow as still images
IMAGE_EXTENSIONS: Set[str] = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".tif",
    ".tiff",
    ".bmp",
    ".ico",
}

VIDEO_EXTENSIONS: Set[str] = {
    ".mp4",
    ".mov",
    ".m4v",
    ".avi",
    ".mkv",
    ".webm",
    ".wmv",
    ".mpg",
    ".mpeg",
    ".3gp",
    ".mts",
    ".m2ts",
    ".ts",
}


def is_image_extension(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def is_video_extension(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def media_kind_for_path(path: Path) -> str:
    """Return 'image' | 'video' | 'other'."""
    suf = path.suffix.lower()
    if suf in IMAGE_EXTENSIONS:
        return "image"
    if suf in VIDEO_EXTENSIONS:
        return "video"
    return "other"


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
        Non-image media → placeholder image (never raises for unsupported formats).
        """
        if not source.is_file():
            raise FileNotFoundError(str(source))

        use_webp = (fmt or ("WEBP" if self.prefer_webp else "JPEG")).upper() == "WEBP"
        ext = "webp" if use_webp else "jpg"
        media_type = "image/webp" if use_webp else "image/jpeg"

        kind = media_kind_for_path(source)
        if kind != "image":
            return self._placeholder(size, kind, source.suffix.lower(), use_webp)

        cache_key = hashlib.sha1(
            f"{source}:{source.stat().st_mtime_ns}:{source.stat().st_size}:{size}:{ext}".encode()
        ).hexdigest()
        cached = self._cache_path(cache_key, ext)
        if cached and cached.is_file():
            return cached.read_bytes(), media_type

        try:
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
        except Exception:
            # Corrupt or exotic still formats — still no 500 for the client
            return self._placeholder(size, "other", source.suffix.lower(), use_webp)

        if cached:
            try:
                cached.write_bytes(data)
            except OSError:
                pass

        return data, media_type

    def _placeholder(
        self,
        size: int,
        kind: str,
        suffix: str,
        use_webp: bool,
    ) -> Tuple[bytes, str]:
        """Simple solid placeholder with a label (VIDEO / FILE)."""
        size = max(64, min(int(size), 1024))
        cache_key = hashlib.sha1(f"placeholder:{kind}:{suffix}:{size}:{use_webp}".encode()).hexdigest()
        ext = "webp" if use_webp else "jpg"
        media_type = "image/webp" if use_webp else "image/jpeg"
        cached = self._cache_path(cache_key, ext)
        if cached and cached.is_file():
            return cached.read_bytes(), media_type

        # Dark card matching UI
        bg = (37, 38, 43)
        fg = (144, 146, 150)
        accent = (77, 171, 247)
        im = Image.new("RGB", (size, size), bg)
        draw = ImageDraw.Draw(im)

        label = "VIDEO" if kind == "video" else "FILE"
        if suffix:
            sub = suffix.lstrip(".").upper()
        else:
            sub = ""

        # Frame
        margin = max(4, size // 16)
        draw.rectangle(
            [margin, margin, size - margin - 1, size - margin - 1],
            outline=accent,
            width=max(1, size // 64),
        )

        # Try default font; size scales with thumb
        font_large = ImageFont.load_default()
        font_small = font_large

        def center_text(text: str, y: int, fill: tuple) -> None:
            bbox = draw.textbbox((0, 0), text, font=font_large)
            tw = bbox[2] - bbox[0]
            x = max(0, (size - tw) // 2)
            draw.text((x, y), text, fill=fill, font=font_large)

        center_text(label, size // 2 - size // 8, accent)
        if sub:
            center_text(sub, size // 2 + size // 12, fg)

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
