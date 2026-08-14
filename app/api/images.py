"""Image metadata, original file and thumbnail endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response

from app.api.deps import get_current_user, get_digikam, get_resolver, get_thumbs
from app.repositories.digikam_repo import DigikamRepository
from app.services.path_resolver import PathResolver
from app.services.thumbnail import (
    ThumbnailService,
    is_image_extension,
    media_kind_for_path,
)

router = APIRouter(prefix="/api", tags=["images"])


@router.get("/images/{image_id}")
def get_image_meta(
    image_id: int,
    user=Depends(get_current_user),
    digikam: DigikamRepository = Depends(get_digikam),
    resolver: PathResolver = Depends(get_resolver),
):
    img = digikam.get_image(image_id)
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    safe = {k: v for k, v in img.items() if k not in ("album_relative_path",)}
    path = resolver.resolve_image(image_id)
    if path:
        kind = media_kind_for_path(path)
        safe["media_kind"] = kind
        safe["previewable"] = kind == "image" and is_image_extension(path)
    else:
        safe["media_kind"] = "other"
        safe["previewable"] = False
    return safe


@router.get("/images/{image_id}/exif")
def get_image_exif(
    image_id: int,
    user=Depends(get_current_user),
    digikam: DigikamRepository = Depends(get_digikam),
):
    """EXIF and related metadata as stored in DigiKam's database."""
    data = digikam.get_image_exif(image_id)
    if not data:
        raise HTTPException(status_code=404, detail="Image not found")
    return data


@router.get("/images/{image_id}/file")
def get_image_file(
    image_id: int,
    user=Depends(get_current_user),
    resolver: PathResolver = Depends(get_resolver),
    thumbs: ThumbnailService = Depends(get_thumbs),
):
    """
    Serve original file for previewable still images.
    For video / unsupported types, serve a large placeholder image instead
    so the lightbox <img> does not break; metadata remains available via /exif.
    """
    path = resolver.resolve_image(image_id)
    if not path:
        raise HTTPException(status_code=404, detail="File not found or not accessible")

    kind = media_kind_for_path(path)
    if kind != "image" or not is_image_extension(path):
        try:
            data, media_type = thumbs.get_thumbnail(path, size=1024)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Placeholder failed: {exc}") from exc
        return Response(
            content=data,
            media_type=media_type,
            headers={"Cache-Control": "private, max-age=86400", "X-Media-Kind": kind},
        )

    suffix = path.suffix.lower()
    media = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".bmp": "image/bmp",
    }.get(suffix, "application/octet-stream")

    return FileResponse(
        path,
        media_type=media,
        filename=path.name,
        content_disposition_type="inline",
    )


@router.get("/images/{image_id}/thumb")
def get_image_thumb(
    image_id: int,
    size: int = Query(320, ge=64, le=1024),
    user=Depends(get_current_user),
    resolver: PathResolver = Depends(get_resolver),
    thumbs: ThumbnailService = Depends(get_thumbs),
):
    path = resolver.resolve_image(image_id)
    if not path:
        raise HTTPException(status_code=404, detail="File not found or not accessible")

    try:
        data, media_type = thumbs.get_thumbnail(path, size=size)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as exc:
        # Last resort — should not happen often after placeholder logic
        raise HTTPException(status_code=500, detail=f"Thumbnail generation failed: {exc}") from exc

    kind = media_kind_for_path(path)
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=86400",
            "X-Media-Kind": kind,
        },
    )
