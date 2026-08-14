"""Album tree and image listing APIs."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, get_digikam
from app.repositories.digikam_repo import DigikamRepository

router = APIRouter(prefix="/api", tags=["albums"])


def _build_album_tree(
    albums: list[dict[str, Any]],
    root_labels: Optional[dict[int, str]] = None,
) -> list[dict[str, Any]]:
    """
    Build a nested tree from the flat Albums list.
    DigiKam stores relativePath like "/2023/Vacation".
    Always includes every album root, even if it has no albums yet.
    """
    root_labels = root_labels or {}

    by_root: dict[int, list] = {}
    for a in albums:
        root_id = a["albumRoot"]
        by_root.setdefault(root_id, []).append(a)

    # Ensure every known root appears, even with zero albums
    for root_id in root_labels:
        by_root.setdefault(root_id, [])

    tree: list[dict[str, Any]] = []

    for root_id, root_albums in sorted(by_root.items()):
        root_albums.sort(key=lambda x: ((x.get("relativePath") or "").count("/"), x.get("relativePath") or ""))

        nodes: dict[str, dict] = {}
        label = root_labels.get(root_id) or f"Collection {root_id}"
        root_node = {
            "id": f"root-{root_id}",
            "digikam_id": None,
            "name": label,
            "relativePath": "/",
            "image_count": 0,
            "children": [],
            "is_root": True,
            "albumRoot": root_id,
        }
        nodes["/"] = root_node

        for a in root_albums:
            rel = a.get("relativePath") or "/"
            if rel == "/":
                root_node["digikam_id"] = a["id"]
                root_node["image_count"] = a.get("image_count") or 0
                root_node["caption"] = a.get("caption")
                continue

            parts = [p for p in rel.split("/") if p]
            current_path = ""
            parent = root_node

            for i, part in enumerate(parts):
                current_path = current_path + "/" + part
                if current_path not in nodes:
                    is_leaf = i == len(parts) - 1
                    node = {
                        "id": f"album-{a['id']}" if is_leaf else f"path-{root_id}-{current_path}",
                        "digikam_id": a["id"] if is_leaf else None,
                        "name": part,
                        "relativePath": current_path,
                        "image_count": a.get("image_count") if is_leaf else 0,
                        "children": [],
                        "is_root": False,
                        "albumRoot": root_id,
                        "caption": a.get("caption") if is_leaf else None,
                    }
                    nodes[current_path] = node
                    parent["children"].append(node)
                parent = nodes[current_path]

        tree.append(root_node)

    return tree


@router.get("/albums")
def list_albums(
    user=Depends(get_current_user),
    digikam: DigikamRepository = Depends(get_digikam),
):
    try:
        albums = digikam.get_albums()
        roots = digikam.get_album_roots()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc

    labels = {r["id"]: (r.get("label") or f"Collection {r['id']}") for r in roots}
    tree = _build_album_tree(albums, root_labels=labels)
    return {"albums": tree, "flat_count": len(albums), "root_count": len(roots)}


@router.get("/albums/{album_id}")
def get_album(
    album_id: int,
    user=Depends(get_current_user),
    digikam: DigikamRepository = Depends(get_digikam),
):
    album = digikam.get_album(album_id)
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    return album


@router.get("/albums/{album_id}/images")
def list_images(
    album_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=200),
    sort: str = Query("name", pattern="^(name|date|rating|id)$"),
    user=Depends(get_current_user),
    digikam: DigikamRepository = Depends(get_digikam),
):
    album = digikam.get_album(album_id)
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")

    images = digikam.get_images_in_album(album_id, offset=offset, limit=limit, sort=sort)
    total = digikam.count_images_in_album(album_id)

    return {
        "album_id": album_id,
        "images": images,
        "offset": offset,
        "limit": limit,
        "total": total,
        "has_more": offset + len(images) < total,
    }
