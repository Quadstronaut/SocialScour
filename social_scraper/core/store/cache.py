"""30-day SQLite LLM-call cache."""
from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Optional


_DEFAULT_TTL_S = 30 * 24 * 3600


class LLMCache:
    def __init__(self, path: Path, ttl_seconds: int = _DEFAULT_TTL_S) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_seconds
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS llm_cache ("
            " key TEXT PRIMARY KEY, value TEXT NOT NULL, written_at REAL NOT NULL"
            ")"
        )
        self._conn.commit()

    @staticmethod
    def make_key(*parts: str) -> str:
        joined = "|".join(sorted(parts))
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[str]:
        now = time.time()
        cur = self._conn.execute(
            "SELECT value, written_at FROM llm_cache WHERE key = ?", (key,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        value, written_at = row
        if now - written_at > self.ttl:
            self._conn.execute("DELETE FROM llm_cache WHERE key = ?", (key,))
            self._conn.commit()
            return None
        return value

    def put(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO llm_cache (key, value, written_at) VALUES (?, ?, ?)",
            (key, value, time.time()),
        )
        self._conn.commit()

    def purge_expired(self) -> int:
        cutoff = time.time() - self.ttl
        cur = self._conn.execute("DELETE FROM llm_cache WHERE written_at < ?", (cutoff,))
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
