"""Application's own SQLite database (config, users, resolved roots)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

import bcrypt


SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT    NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS album_roots (
    digikam_id    INTEGER PRIMARY KEY,
    label         TEXT,
    status        INTEGER,
    type          INTEGER,
    identifier    TEXT,
    specific_path TEXT NOT NULL,
    relative_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
"""


class AppDB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def session(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.session() as conn:
            conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ config
    def set_config(self, key: str, value: str) -> None:
        with self.session() as conn:
            conn.execute(
                "INSERT INTO config(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self.session() as conn:
            row = conn.execute(
                "SELECT value FROM config WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default

    def get_all_config(self) -> dict[str, str]:
        with self.session() as conn:
            rows = conn.execute("SELECT key, value FROM config").fetchall()
            return {r["key"]: r["value"] for r in rows}

    # ------------------------------------------------------------------ users
    @staticmethod
    def _hash_password(password: str) -> str:
        # bcrypt has a 72-byte limit; reject obvious mistakes early
        raw = password.encode("utf-8")
        if len(raw) > 72:
            raise ValueError("Password is too long (bcrypt limit is 72 bytes)")
        return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("ascii")

    @staticmethod
    def _check_password(password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(
                password.encode("utf-8"),
                password_hash.encode("ascii"),
            )
        except Exception:
            return False

    def create_user(self, username: str, password: str, is_admin: bool = False) -> int:
        username = (username or "").strip()
        password = password or ""
        if not username:
            raise ValueError("Username must not be empty")
        if not password:
            raise ValueError("Password must not be empty")

        hashed = self._hash_password(password)
        now = datetime.now(timezone.utc).isoformat()
        with self.session() as conn:
            cur = conn.execute(
                "INSERT INTO users(username, password_hash, is_admin, created_at) "
                "VALUES(?, ?, ?, ?)",
                (username, hashed, 1 if is_admin else 0, now),
            )
            user_id = int(cur.lastrowid)

        # Immediate round-trip check so init/user-add cannot silently store a bad hash
        if not self.verify_user(username, password):
            with self.session() as conn:
                conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            raise RuntimeError(
                "Password hash verification failed immediately after create; "
                "user was not saved. Please try again."
            )
        return user_id

    def verify_user(self, username: str, password: str) -> Optional[dict[str, Any]]:
        username = (username or "").strip()
        password = password or ""
        if not username or not password:
            return None
        with self.session() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash, is_admin FROM users "
                "WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
            if not row:
                return None
            if not self._check_password(password, row["password_hash"]):
                return None
            return {
                "id": row["id"],
                "username": row["username"],
                "is_admin": bool(row["is_admin"]),
            }

    def update_password(self, username: str, password: str) -> bool:
        username = (username or "").strip()
        password = password or ""
        if not username or not password:
            return False
        hashed = self._hash_password(password)
        with self.session() as conn:
            cur = conn.execute(
                "UPDATE users SET password_hash = ? WHERE username = ? COLLATE NOCASE",
                (hashed, username),
            )
            if cur.rowcount == 0:
                return False
        return self.verify_user(username, password) is not None

    def list_users(self) -> list[dict[str, Any]]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT id, username, is_admin, created_at FROM users ORDER BY username"
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_user(self, username: str) -> bool:
        username = (username or "").strip()
        with self.session() as conn:
            cur = conn.execute(
                "DELETE FROM users WHERE username = ? COLLATE NOCASE", (username,)
            )
            return cur.rowcount > 0

    def user_count(self) -> int:
        with self.session() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    # ------------------------------------------------------------------ album roots
    def clear_album_roots(self) -> None:
        with self.session() as conn:
            conn.execute("DELETE FROM album_roots")

    def upsert_album_root(
        self,
        digikam_id: int,
        label: str,
        status: int,
        type_: int,
        identifier: str,
        specific_path: str,
        relative_path: str = "",
    ) -> None:
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO album_roots
                    (digikam_id, label, status, type, identifier, specific_path, relative_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(digikam_id) DO UPDATE SET
                    label=excluded.label,
                    status=excluded.status,
                    type=excluded.type,
                    identifier=excluded.identifier,
                    specific_path=excluded.specific_path,
                    relative_path=excluded.relative_path
                """,
                (digikam_id, label, status, type_, identifier, specific_path, relative_path),
            )

    def get_album_roots(self) -> list[dict[str, Any]]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT * FROM album_roots ORDER BY digikam_id"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_album_root(self, digikam_id: int) -> Optional[dict[str, Any]]:
        with self.session() as conn:
            row = conn.execute(
                "SELECT * FROM album_roots WHERE digikam_id = ?", (digikam_id,)
            ).fetchone()
            return dict(row) if row else None
