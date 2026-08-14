"""Image metadata, original file and thumbnail endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response

from app.api.deps import get_current_user, get_digikam, get_resolver, get_thumbs
from app.repositories.digikam_repo import DigikamRepository
from app.services.path_resolver import PathResolver
from app.services.thumbnail import ThumbnailService

router = APIRouter(prefix="/api", tags=["images"])


@router.get("/images/{image_id}")
def get_image_meta(
    image_id: int,
    user=Depends(get_current_user),
    digikam: DigikamRepository = Depends(get_digikam),
):
    img = digikam.get_image(image_id)
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    safe = {k: v for k, v in img.items() if k not in ("album_relative_path",)}
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
):
    path = resolver.resolve_image(image_id)
    if not path:
        raise HTTPException(status_code=404, detail="File not found or not accessible")

    suffix = path.suffix.lower()
    media = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".heic": "image/heic",
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Thumbnail generation failed: {exc}")

    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )
