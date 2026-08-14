"""Read-only repository for DigiKam's core SQLite database.

This is the single place that talks to digikam4.db.
Designed so a future MySQL implementation can implement the same interface.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional


class DigikamRepository:
    """Read-only access to digikam4.db (core database)."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        if not self.db_path.is_file():
            raise FileNotFoundError(f"DigiKam core database not found: {self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self.db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Keep reads snappy on large DBs
        conn.execute("PRAGMA query_only = ON")
        return conn

    @contextmanager
    def session(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------------ AlbumRoots
    def get_album_roots(self) -> list[dict[str, Any]]:
        with self.session() as conn:
            rows = conn.execute(
                """
                SELECT id, label, status, type, identifier, specificPath
                FROM AlbumRoots
                ORDER BY id
                """
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------ Albums (tree)
    def get_albums(self) -> list[dict[str, Any]]:
        """Return all albums. Image counts are loaded separately when needed."""
        with self.session() as conn:
            # Avoid correlated COUNT(*) here – it is very slow on large collections
            # and blocked the album-tree UI.
            rows = conn.execute(
                """
                SELECT
                    a.id,
                    a.albumRoot,
                    a.relativePath,
                    a.date,
                    a.caption,
                    a.collection,
                    a.icon,
                    a.modificationDate
                FROM Albums a
                ORDER BY a.albumRoot, a.relativePath
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def get_album(self, album_id: int) -> Optional[dict[str, Any]]:
        with self.session() as conn:
            row = conn.execute(
                """
                SELECT
                    a.id,
                    a.albumRoot,
                    a.relativePath,
                    a.date,
                    a.caption,
                    a.collection,
                    a.icon,
                    a.modificationDate,
                    (SELECT COUNT(*) FROM Images i WHERE i.album = a.id AND i.status = 1) AS image_count
                FROM Albums a
                WHERE a.id = ?
                """,
                (album_id,),
            ).fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------------ Images
    def get_images_in_album(
        self,
        album_id: int,
        offset: int = 0,
        limit: int = 60,
        sort: str = "name",
    ) -> list[dict[str, Any]]:
        """Paginated list of images belonging to an album (status=1 = visible)."""
        order_map = {
            "name": "i.name COLLATE NOCASE",
            "date": "ii.creationDate",
            "rating": "ii.rating DESC",
            "id": "i.id",
        }
        order_by = order_map.get(sort, order_map["name"])

        with self.session() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    i.id,
                    i.name,
                    i.album,
                    i.uniqueHash,
                    i.status,
                    i.category,
                    i.modificationDate,
                    i.fileSize,
                    ii.rating,
                    ii.creationDate,
                    ii.digitizationDate,
                    ii.width,
                    ii.height,
                    ii.orientation,
                    ii.format
                FROM Images i
                LEFT JOIN ImageInformation ii ON ii.imageid = i.id
                WHERE i.album = ? AND i.status = 1
                ORDER BY {order_by}
                LIMIT ? OFFSET ?
                """,
                (album_id, limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]

    def count_images_in_album(self, album_id: int) -> int:
        with self.session() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM Images WHERE album = ? AND status = 1",
                (album_id,),
            ).fetchone()
            return int(row["cnt"]) if row else 0

    def get_image(self, image_id: int) -> Optional[dict[str, Any]]:
        with self.session() as conn:
            row = conn.execute(
                """
                SELECT
                    i.id,
                    i.name,
                    i.album,
                    i.uniqueHash,
                    i.status,
                    i.category,
                    i.modificationDate,
                    i.fileSize,
                    ii.rating,
                    ii.creationDate,
                    ii.digitizationDate,
                    ii.width,
                    ii.height,
                    ii.orientation,
                    ii.format,
                    ii.colorDepth,
                    ii.colorModel,
                    a.albumRoot,
                    a.relativePath AS album_relative_path
                FROM Images i
                LEFT JOIN ImageInformation ii ON ii.imageid = i.id
                LEFT JOIN Albums a ON a.id = i.album
                WHERE i.id = ? AND i.status = 1
                """,
                (image_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_image_exif(self, image_id: int) -> Optional[dict[str, Any]]:
        """
        Return structured metadata DigiKam extracted from the file (and DB fields).
        Combines Images, ImageInformation, ImageMetadata, ImagePositions, comments.
        """
        base = self.get_image(image_id)
        if not base:
            return None

        meta = pos = None
        comments = []
        with self.session() as conn:
            try:
                meta = conn.execute(
                    """
                    SELECT
                        make, model, lens, aperture, focalLength, focalLength35,
                        exposureTime, exposureProgram, exposureMode, sensitivity,
                        flash, whiteBalance, whiteBalanceColorTemperature,
                        meteringMode, subjectDistance, subjectDistanceCategory
                    FROM ImageMetadata
                    WHERE imageid = ?
                    """,
                    (image_id,),
                ).fetchone()
            except Exception:
                meta = None

            try:
                pos = conn.execute(
                    """
                    SELECT latitude, latitudeNumber, longitude, longitudeNumber,
                           altitude, orientation, tilt, roll, accuracy
                    FROM ImagePositions
                    WHERE imageid = ?
                    """,
                    (image_id,),
                ).fetchone()
            except Exception:
                pos = None

            try:
                comments = conn.execute(
                    """
                    SELECT type, language, author, date, comment
                    FROM ImageComments
                    WHERE imageid = ?
                    ORDER BY type, language
                    """,
                    (image_id,),
                ).fetchall()
            except Exception:
                comments = []

        def fmt_exposure(t):
            if t is None:
                return None
            try:
                t = float(t)
            except (TypeError, ValueError):
                return str(t)
            if t <= 0:
                return str(t)
            if t >= 1:
                return f"{t:g} s"
            inv = round(1 / t)
            if abs(1 / inv - t) < 1e-6:
                return f"1/{inv} s"
            return f"{t:g} s"

        def fmt_aperture(a):
            if a is None:
                return None
            try:
                return f"f/{float(a):g}"
            except (TypeError, ValueError):
                return str(a)

        def fmt_focal(f):
            if f is None:
                return None
            try:
                return f"{float(f):g} mm"
            except (TypeError, ValueError):
                return str(f)

        meta_d = dict(meta) if meta else {}
        pos_d = dict(pos) if pos else {}

        # Build ordered display sections (label, value) — skip empty
        sections = []

        general = [
            ("File", base.get("name")),
            ("Format", base.get("format")),
            ("Size", f"{base['width']} × {base['height']}" if base.get("width") and base.get("height") else None),
            ("File size", f"{base['fileSize']:,} bytes" if base.get("fileSize") else None),
            ("Orientation", base.get("orientation")),
            ("Color depth", base.get("colorDepth")),
            ("Color model", base.get("colorModel")),
            ("Rating", base.get("rating")),
            ("Date taken", base.get("creationDate")),
            ("Digitized", base.get("digitizationDate")),
            ("Modified", base.get("modificationDate")),
        ]
        sections.append(("File / Image", [(k, v) for k, v in general if v not in (None, "")]))

        camera = [
            ("Make", meta_d.get("make")),
            ("Model", meta_d.get("model")),
            ("Lens", meta_d.get("lens")),
            ("Aperture", fmt_aperture(meta_d.get("aperture"))),
            ("Focal length", fmt_focal(meta_d.get("focalLength"))),
            ("Focal length (35mm)", fmt_focal(meta_d.get("focalLength35"))),
            ("Exposure", fmt_exposure(meta_d.get("exposureTime"))),
            ("ISO", meta_d.get("sensitivity")),
            ("Flash", meta_d.get("flash")),
            ("White balance", meta_d.get("whiteBalance")),
            ("WB temperature", meta_d.get("whiteBalanceColorTemperature")),
            ("Metering", meta_d.get("meteringMode")),
            ("Exposure program", meta_d.get("exposureProgram")),
            ("Exposure mode", meta_d.get("exposureMode")),
            ("Subject distance", meta_d.get("subjectDistance")),
        ]
        sections.append(("Camera / EXIF", [(k, v) for k, v in camera if v not in (None, "")]))

        gps = [
            ("Latitude", pos_d.get("latitude") or pos_d.get("latitudeNumber")),
            ("Longitude", pos_d.get("longitude") or pos_d.get("longitudeNumber")),
            ("Altitude", pos_d.get("altitude")),
            ("GPS accuracy", pos_d.get("accuracy")),
        ]
        gps_items = [(k, v) for k, v in gps if v not in (None, "")]
        if gps_items:
            sections.append(("Location", gps_items))

        # Numeric geo for map links (prefer *Number columns)
        geo = None
        try:
            lat = pos_d.get("latitudeNumber")
            lon = pos_d.get("longitudeNumber")
            if lat is None and pos_d.get("latitude") is not None:
                lat = float(str(pos_d.get("latitude")).replace(",", ".").split()[0])
            if lon is None and pos_d.get("longitude") is not None:
                lon = float(str(pos_d.get("longitude")).replace(",", ".").split()[0])
            if lat is not None and lon is not None:
                lat_f, lon_f = float(lat), float(lon)
                if -90 <= lat_f <= 90 and -180 <= lon_f <= 180:
                    alt = pos_d.get("altitude")
                    try:
                        alt_f = float(alt) if alt is not None else None
                    except (TypeError, ValueError):
                        alt_f = None
                    geo = {"lat": lat_f, "lon": lon_f, "altitude": alt_f}
        except (TypeError, ValueError):
            geo = None

        comment_items = []
        for c in comments or []:
            text = (c["comment"] or "").strip()
            if text:
                label = {1: "Comment", 3: "Title", 4: "Caption"}.get(c["type"], f"Type {c['type']}")
                if c["language"] and c["language"] != "x-default":
                    label = f"{label} ({c['language']})"
                comment_items.append((label, text))
        if comment_items:
            sections.append(("Comments", comment_items))

        return {
            "id": base["id"],
            "name": base.get("name"),
            "geo": geo,
            "sections": [
                {"title": title, "fields": [{"label": k, "value": str(v)} for k, v in items]}
                for title, items in sections
                if items
            ],
        }

    def get_image_by_unique_hash(self, unique_hash: str) -> Optional[dict[str, Any]]:
        with self.session() as conn:
            row = conn.execute(
                "SELECT id, name, album FROM Images WHERE uniqueHash = ? AND status = 1",
                (unique_hash,),
            ).fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------------ Dates (View by Date)
    def get_date_tree(self) -> list[dict[str, Any]]:
        """
        Build year → month → day counts from ImageInformation.creationDate.
        DigiKam stores creationDate as text (often 'YYYY-MM-DDTHH:MM:SS').
        """
        with self.session() as conn:
            rows = conn.execute(
                """
                SELECT
                    substr(ii.creationDate, 1, 4) AS year,
                    substr(ii.creationDate, 6, 2) AS month,
                    substr(ii.creationDate, 9, 2) AS day,
                    COUNT(*) AS cnt
                FROM Images i
                JOIN ImageInformation ii ON ii.imageid = i.id
                WHERE i.status = 1
                  AND ii.creationDate IS NOT NULL
                  AND length(ii.creationDate) >= 10
                  AND substr(ii.creationDate, 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
                GROUP BY year, month, day
                ORDER BY year DESC, month DESC, day DESC
                """
            ).fetchall()

        # Nest into year → month → day
        years: dict[str, dict] = {}
        for r in rows:
            y, m, d, cnt = r["year"], r["month"], r["day"], int(r["cnt"])
            if y not in years:
                years[y] = {
                    "year": y,
                    "count": 0,
                    "months": {},
                }
            years[y]["count"] += cnt
            months = years[y]["months"]
            if m not in months:
                months[m] = {
                    "month": m,
                    "count": 0,
                    "days": [],
                }
            months[m]["count"] += cnt
            months[m]["days"].append({"day": d, "count": cnt})

        result = []
        for y in sorted(years.keys(), reverse=True):
            ynode = years[y]
            month_list = []
            for m in sorted(ynode["months"].keys(), reverse=True):
                mnode = ynode["months"][m]
                month_list.append({
                    "month": m,
                    "count": mnode["count"],
                    "days": mnode["days"],
                })
            result.append({
                "year": ynode["year"],
                "count": ynode["count"],
                "months": month_list,
            })
        return result

    def get_images_by_date(
        self,
        year: Optional[str] = None,
        month: Optional[str] = None,
        day: Optional[str] = None,
        offset: int = 0,
        limit: int = 60,
        sort: str = "date",
    ) -> list[dict[str, Any]]:
        """Images matching a year / year-month / year-month-day prefix on creationDate."""
        prefix = ""
        if year:
            prefix = year
            if month:
                prefix = f"{year}-{month}"
                if day:
                    prefix = f"{year}-{month}-{day}"

        if not prefix:
            return []

        order_map = {
            "name": "i.name COLLATE NOCASE",
            "date": "ii.creationDate DESC",
            "rating": "ii.rating DESC",
            "id": "i.id",
        }
        order_by = order_map.get(sort, order_map["date"])

        with self.session() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    i.id,
                    i.name,
                    i.album,
                    i.uniqueHash,
                    i.status,
                    i.category,
                    i.modificationDate,
                    i.fileSize,
                    ii.rating,
                    ii.creationDate,
                    ii.digitizationDate,
                    ii.width,
                    ii.height,
                    ii.orientation,
                    ii.format
                FROM Images i
                JOIN ImageInformation ii ON ii.imageid = i.id
                WHERE i.status = 1
                  AND ii.creationDate IS NOT NULL
                  AND ii.creationDate LIKE ? || '%'
                ORDER BY {order_by}
                LIMIT ? OFFSET ?
                """,
                (prefix, limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]

    def count_images_by_date(
        self,
        year: Optional[str] = None,
        month: Optional[str] = None,
        day: Optional[str] = None,
    ) -> int:
        prefix = ""
        if year:
            prefix = year
            if month:
                prefix = f"{year}-{month}"
                if day:
                    prefix = f"{year}-{month}-{day}"
        if not prefix:
            return 0
        with self.session() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM Images i
                JOIN ImageInformation ii ON ii.imageid = i.id
                WHERE i.status = 1
                  AND ii.creationDate IS NOT NULL
                  AND ii.creationDate LIKE ? || '%'
                """,
                (prefix,),
            ).fetchone()
            return int(row["cnt"]) if row else 0
