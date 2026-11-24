"""Local SQLite cache for public filing data.

The cache file lives on your machine only (default ``~/.opentearsheet/cache.sqlite3``)
and holds raw responses from public SEC endpoints. Delete it any time.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS http_cache (
    url          TEXT PRIMARY KEY,
    fetched_at   REAL NOT NULL,
    status       INTEGER NOT NULL,
    content_type TEXT,
    body         BLOB NOT NULL
)
"""


@dataclass(frozen=True)
class CachedResponse:
    url: str
    fetched_at: float
    status: int
    content_type: str
    body: bytes


class HttpCache:
    def __init__(self, path: str | os.PathLike = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            p = Path(self.path).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            try:  # keep research history private to the current OS user
                os.chmod(p.parent, 0o700)
            except OSError:
                pass
            self.path = str(p)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        with self._lock:
            self._conn.execute(SCHEMA)
            self._conn.commit()

    def get(self, url: str, max_age: Optional[float] = None, now: Optional[float] = None) -> Optional[CachedResponse]:
        """Return a cached response, or None if missing or older than ``max_age`` seconds."""
        with self._lock:
            row = self._conn.execute(
                "SELECT url, fetched_at, status, content_type, body FROM http_cache WHERE url = ?",
                (url,),
            ).fetchone()
        if row is None:
            return None
        resp = CachedResponse(row[0], row[1], row[2], row[3] or "", bytes(row[4]))
        current = time.time() if now is None else now
        if max_age is not None and current - resp.fetched_at > max_age:
            return None
        return resp

    def put(self, url: str, status: int, content_type: str, body: bytes, now: Optional[float] = None) -> None:
        fetched_at = time.time() if now is None else now
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO http_cache (url, fetched_at, status, content_type, body) VALUES (?, ?, ?, ?, ?)",
                (url, fetched_at, status, content_type, sqlite3.Binary(body)),
            )
            self._conn.commit()

    def stats(self) -> dict:
        with self._lock:
            entries, size = self._conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(body)), 0) FROM http_cache"
            ).fetchone()
        return {"entries": entries, "bytes": size, "path": self.path}

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM http_cache")
            self._conn.commit()
            self._conn.execute("VACUUM")

    def close(self) -> None:
        with self._lock:
            self._conn.close()
