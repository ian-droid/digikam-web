"""Tags tree and images-by-tag APIs."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, get_digikam
from app.repositories.digikam_repo import DigikamRepository

router = APIRouter(prefix="/api", tags=["tags"])


def _build_tag_tree(
    tags: list[dict[str, Any]],
    people_only: bool = False,
) -> list[dict[str, Any]]:
    """
    Build nested tree from flat Tags rows (pid parent).
    people_only: keep person tags and ancestors needed to show them.
    """
    by_id: dict[int, dict[str, Any]] = {}
    for t in tags:
        tid = int(t["id"])
        by_id[tid] = {
            "id": tid,
            "name": t.get("name") or "(unnamed)",
            "pid": t.get("pid"),
            "is_person": bool(t.get("is_person")),
            "children": [],
        }

    # Parent links
    roots: list[dict[str, Any]] = []
    for node in by_id.values():
        pid = node["pid"]
        if pid is not None and int(pid) in by_id and int(pid) != node["id"]:
            by_id[int(pid)]["children"].append(node)
        else:
            roots.append(node)

    def sort_rec(nodes: list[dict[str, Any]]) -> None:
        nodes.sort(key=lambda n: (n["name"] or "").lower())
        for n in nodes:
            sort_rec(n["children"])

    sort_rec(roots)

    if not people_only:
        return roots

    # Keep nodes that are persons or have a person descendant
    def prune(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept: list[dict[str, Any]] = []
        for n in nodes:
            kids = prune(n["children"])
            if n["is_person"] or kids:
                kept.append({**n, "children": kids})
        return kept

    return prune(roots)


@router.get("/tags")
def list_tags(
    people_only: bool = Query(False),
    user=Depends(get_current_user),
    digikam: DigikamRepository = Depends(get_digikam),
):
    try:
        flat = digikam.get_tags()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc

    tree = _build_tag_tree(flat, people_only=people_only)
    person_count = sum(1 for t in flat if t.get("is_person"))
    return {
        "tags": tree,
        "flat_count": len(flat),
        "person_count": person_count,
        "people_only": people_only,
    }


@router.get("/tags/{tag_id}/images")
def list_images_by_tag(
    tag_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=200),
    sort: str = Query("name", pattern="^(name|date|rating|id)$"),
    include_children: bool = Query(
        False,
        description="Include images tagged with direct child tags / TagsTree descendants",
    ),
    user=Depends(get_current_user),
    digikam: DigikamRepository = Depends(get_digikam),
):
    images = digikam.get_images_by_tag(
        tag_id,
        offset=offset,
        limit=limit,
        sort=sort,
        include_children=include_children,
    )
    total = digikam.count_images_by_tag(tag_id, include_children=include_children)
    return {
        "tag_id": tag_id,
        "images": images,
        "offset": offset,
        "limit": limit,
        "total": total,
        "has_more": offset + len(images) < total,
        "include_children": include_children,
    }
