"""View by Date APIs."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, get_digikam
from app.repositories.digikam_repo import DigikamRepository

router = APIRouter(prefix="/api", tags=["dates"])

MONTH_NAMES = {
    "01": "January", "02": "February", "03": "March", "04": "April",
    "05": "May", "06": "June", "07": "July", "08": "August",
    "09": "September", "10": "October", "11": "November", "12": "December",
}


@router.get("/dates")
def list_dates(
    user=Depends(get_current_user),
    digikam: DigikamRepository = Depends(get_digikam),
):
    try:
        tree = digikam.get_date_tree()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc

    # Attach display labels
    for y in tree:
        for m in y.get("months", []):
            m["label"] = MONTH_NAMES.get(m["month"], m["month"])
    return {"dates": tree}


@router.get("/dates/images")
def list_images_by_date(
    year: Optional[str] = Query(None, pattern=r"^\d{4}$"),
    month: Optional[str] = Query(None, pattern=r"^\d{2}$"),
    day: Optional[str] = Query(None, pattern=r"^\d{2}$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=200),
    sort: str = Query("date", pattern="^(name|date|rating|id)$"),
    user=Depends(get_current_user),
    digikam: DigikamRepository = Depends(get_digikam),
):
    if not year:
        raise HTTPException(status_code=400, detail="year is required")
    if day and not month:
        raise HTTPException(status_code=400, detail="month is required when day is set")

    images = digikam.get_images_by_date(
        year=year, month=month, day=day, offset=offset, limit=limit, sort=sort
    )
    total = digikam.count_images_by_date(year=year, month=month, day=day)

    label_parts = [year]
    if month:
        label_parts.append(MONTH_NAMES.get(month, month))
    if day:
        label_parts.append(day.lstrip("0") or day)

    return {
        "year": year,
        "month": month,
        "day": day,
        "label": " / ".join(label_parts),
        "images": images,
        "offset": offset,
        "limit": limit,
        "total": total,
        "has_more": offset + len(images) < total,
    }
