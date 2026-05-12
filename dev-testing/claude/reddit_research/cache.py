"""SQLite cache layer — §13 of v1.spec."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .schema import PostSummary, PromptRow, RawPost

_DDL = """
CREATE TABLE IF NOT EXISTS prompts (
    prompt_hash    TEXT PRIMARY KEY,
    prompt_text    TEXT NOT NULL,
    ran_at         TEXT NOT NULL,
    subreddits     TEXT NOT NULL,
    post_ids       TEXT NOT NULL,
    digest_md_path TEXT,
    digest_json    TEXT
);
CREATE TABLE IF NOT EXISTS posts (
    post_id    TEXT PRIMARY KEY,
    subreddit  TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    raw_json   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS summaries (
    post_id       TEXT NOT NULL,
    model         TEXT NOT NULL,
    summarized_at TEXT NOT NULL,
    summary_json  TEXT NOT NULL,
    PRIMARY KEY (post_id, model)
);
CREATE INDEX IF NOT EXISTS idx_posts_fetched_at ON posts(fetched_at);
CREATE INDEX IF NOT EXISTS idx_prompts_ran_at   ON prompts(ran_at);
"""

_PUNCTUATION = re.compile(r"[^\w\s?]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize_prompt(text: str) -> str:
    text = text.lower()
    text = _PUNCTUATION.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


def hash_prompt(text: str, listing: str, time_filter: str) -> str:
    key = f"{normalize_prompt(text)}|{listing}|{time_filter}"
    return hashlib.sha256(key.encode()).hexdigest()


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Cache:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA foreign_keys=ON")
        self._con.executescript(_DDL)
        self.purge()

    def purge(self, days: int = 30) -> dict[str, int]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        counts: dict[str, int] = {}
        self._con.execute("BEGIN")
        try:
            for table, col in (
                ("posts", "fetched_at"),
                ("prompts", "ran_at"),
                ("summaries", "summarized_at"),
            ):
                cur = self._con.execute(
                    f"DELETE FROM {table} WHERE {col} < ?", (cutoff,)
                )
                counts[table] = cur.rowcount
            self._con.execute("COMMIT")
        except Exception:
            self._con.execute("ROLLBACK")
            raise
        return counts

    def get_post(self, post_id: str) -> RawPost | None:
        row = self._con.execute(
            "SELECT raw_json, fetched_at FROM posts WHERE post_id = ?", (post_id,)
        ).fetchone()
        if row is None:
            return None
        raw_json, fetched_at_str = row
        fetched_at = datetime.fromisoformat(fetched_at_str.rstrip("Z")).replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - fetched_at > timedelta(hours=24):
            return None
        return RawPost.model_validate_json(raw_json)

    def put_post(self, post: RawPost) -> None:
        self._con.execute("BEGIN")
        try:
            self._con.execute(
                """INSERT INTO posts (post_id, subreddit, fetched_at, raw_json)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(post_id) DO UPDATE SET
                       subreddit  = excluded.subreddit,
                       fetched_at = excluded.fetched_at,
                       raw_json   = excluded.raw_json""",
                (post.id, post.subreddit, _utcnow(), post.model_dump_json()),
            )
            self._con.execute("COMMIT")
        except Exception:
            self._con.execute("ROLLBACK")
            raise

    def get_summary(self, post_id: str, model: str) -> PostSummary | None:
        row = self._con.execute(
            "SELECT summary_json FROM summaries WHERE post_id = ? AND model = ?",
            (post_id, model),
        ).fetchone()
        if row is None:
            return None
        return PostSummary.model_validate_json(row[0])

    def put_summary(self, post_id: str, model: str, summary: PostSummary) -> None:
        self._con.execute("BEGIN")
        try:
            self._con.execute(
                """INSERT INTO summaries (post_id, model, summarized_at, summary_json)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(post_id, model) DO UPDATE SET
                       summarized_at = excluded.summarized_at,
                       summary_json  = excluded.summary_json""",
                (post_id, model, _utcnow(), summary.model_dump_json()),
            )
            self._con.execute("COMMIT")
        except Exception:
            self._con.execute("ROLLBACK")
            raise

    def get_prompt(self, prompt_hash: str) -> PromptRow | None:
        row = self._con.execute(
            "SELECT prompt_hash, prompt_text, ran_at, subreddits, post_ids, digest_md_path, digest_json "
            "FROM prompts WHERE prompt_hash = ?",
            (prompt_hash,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_prompt(row)

    def put_prompt(self, row: PromptRow) -> None:
        self._con.execute("BEGIN")
        try:
            self._con.execute(
                """INSERT INTO prompts
                       (prompt_hash, prompt_text, ran_at, subreddits, post_ids, digest_md_path, digest_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(prompt_hash) DO UPDATE SET
                       prompt_text    = excluded.prompt_text,
                       ran_at         = excluded.ran_at,
                       subreddits     = excluded.subreddits,
                       post_ids       = excluded.post_ids,
                       digest_md_path = excluded.digest_md_path,
                       digest_json    = excluded.digest_json""",
                (
                    row.prompt_hash,
                    row.prompt_text,
                    row.ran_at,
                    json.dumps(row.subreddits),
                    json.dumps(row.post_ids),
                    row.digest_md_path,
                    row.digest_json,
                ),
            )
            self._con.execute("COMMIT")
        except Exception:
            self._con.execute("ROLLBACK")
            raise

    def list_prompts(self, limit: int = 20) -> list[PromptRow]:
        rows = self._con.execute(
            "SELECT prompt_hash, prompt_text, ran_at, subreddits, post_ids, digest_md_path, digest_json "
            "FROM prompts ORDER BY ran_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_prompt(r) for r in rows]

    @staticmethod
    def _row_to_prompt(row: tuple) -> PromptRow:
        ph, pt, ra, subs, pids, mdp, dj = row
        return PromptRow(
            prompt_hash=ph,
            prompt_text=pt,
            ran_at=ra,
            subreddits=json.loads(subs),
            post_ids=json.loads(pids),
            digest_md_path=mdp,
            digest_json=dj,
        )

    def search_summaries(
        self,
        query: str,
        subreddit: str | None = None,
        limit: int = 10,
    ) -> list[tuple[str, str, str, str]]:
        q = query.lower()
        sql = (
            "SELECT p.post_id, p.raw_json, p.subreddit, s.summary_json "
            "FROM posts p JOIN summaries s ON p.post_id = s.post_id"
        )
        params: list[str] = []
        if subreddit:
            sql += " WHERE p.subreddit = ?"
            params.append(subreddit)
        rows = self._con.execute(sql, params).fetchall()
        results: list[tuple[str, str, str, str]] = []
        for post_id, raw_json, sub, summary_json in rows:
            post = json.loads(raw_json)
            summary = json.loads(summary_json)
            title = post.get("title", "")
            one_sentence = summary.get("one_sentence", "")
            if q in title.lower() or q in one_sentence.lower():
                results.append((post_id, title, sub, one_sentence))
            if len(results) >= limit:
                break
        return results

    def stats(self) -> dict:
        counts = {}
        for table in ("posts", "prompts", "summaries"):
            row = self._con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts[table] = row[0]
        counts["db_size_bytes"] = self._path.stat().st_size if self._path.exists() else 0
        return counts

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> "Cache":
        return self

    def __exit__(self, *_) -> None:
        self.close()
