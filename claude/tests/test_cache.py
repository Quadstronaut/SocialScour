"""Tests for cache.py — §18 of v1.spec."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from reddit_research.cache import Cache, hash_prompt, normalize_prompt
from reddit_research.schema import PostSummary, PromptRow, RawPost


def _make_post(post_id: str = "abc123") -> RawPost:
    return RawPost(
        id=post_id,
        subreddit="python",
        title="How to use asyncio",
        author="alice",
        url="https://reddit.com/r/python/abc123",
        permalink="https://www.reddit.com/r/python/abc123",
        selftext="Some body text here.",
        score=42,
        upvote_ratio=0.95,
        num_comments=7,
        created_utc=1_700_000_000.0,
    )


def _make_summary(post_id: str = "abc123") -> PostSummary:
    return PostSummary(
        post_id=post_id,
        one_sentence="Short summary of the post.",
        three_bullets=["Bullet one.", "Bullet two.", "Bullet three."],
        key_quotes=["quote one"],
        sentiment="positive",
        topics=["asyncio", "python"],
        relevance_to_prompt=0.8,
    )


def _make_prompt_row(h: str = "deadbeef") -> PromptRow:
    return PromptRow(
        prompt_hash=h,
        prompt_text="How do asyncio tasks work?",
        ran_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        subreddits=["python"],
        post_ids=["abc123"],
        digest_md_path=None,
        digest_json='{"prompt":"test","generated_utc":"2026-05-11T00:00:00Z",'
                    '"subreddits_used":["python"],"post_count":1,"themes":[],'
                    '"narrative":"test","notable_posts":[],"per_sub_sentiment":[]}',
    )


# 1. Tables created on init
def test_tables_created(tmp_path: Path) -> None:
    db = tmp_path / "cache.db"
    with Cache(db) as c:
        rows = c._con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {r[0] for r in rows}
    assert {"posts", "prompts", "summaries"}.issubset(names)


# 2. put_post / get_post round-trip
def test_put_get_post(tmp_path: Path) -> None:
    db = tmp_path / "cache.db"
    post = _make_post()
    with Cache(db) as c:
        c.put_post(post)
        result = c.get_post(post.id)
    assert result is not None
    assert result.id == post.id
    assert result.title == post.title


# 3. get_post returns None for stale entry
def test_get_post_stale(tmp_path: Path) -> None:
    db = tmp_path / "cache.db"
    post = _make_post()
    with Cache(db) as c:
        c.put_post(post)
        stale = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c._con.execute("UPDATE posts SET fetched_at = ? WHERE post_id = ?", (stale, post.id))
        result = c.get_post(post.id)
    assert result is None


# 4. put_summary / get_summary round-trip
def test_put_get_summary(tmp_path: Path) -> None:
    db = tmp_path / "cache.db"
    summary = _make_summary()
    with Cache(db) as c:
        c.put_summary("abc123", "qwen3-coder:30b", summary)
        result = c.get_summary("abc123", "qwen3-coder:30b")
    assert result is not None
    assert result.one_sentence == summary.one_sentence
    assert result.three_bullets == summary.three_bullets


# 5. purge removes old rows, keeps recent
def test_purge(tmp_path: Path) -> None:
    db = tmp_path / "cache.db"
    now = datetime.now(timezone.utc)
    old_ts = (now - timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_ts = (now - timedelta(days=29)).strftime("%Y-%m-%dT%H:%M:%SZ")

    with Cache(db) as c:
        # insert old post
        old_post = _make_post("old1")
        c.put_post(old_post)
        c._con.execute("UPDATE posts SET fetched_at = ? WHERE post_id = ?", (old_ts, "old1"))

        # insert new post
        new_post = _make_post("new1")
        c.put_post(new_post)
        c._con.execute("UPDATE posts SET fetched_at = ? WHERE post_id = ?", (new_ts, "new1"))

        counts = c.purge(days=30)

        remaining = c._con.execute("SELECT post_id FROM posts").fetchall()
        ids = {r[0] for r in remaining}

    assert counts["posts"] >= 1
    assert "old1" not in ids
    assert "new1" in ids


# 6. hash_prompt is stable and sensitive to listing
def test_hash_prompt_stability(tmp_path: Path) -> None:
    h1 = hash_prompt("Hello World", "top", "month")
    h2 = hash_prompt("hello   world", "top", "month")
    assert h1 == h2

    h3 = hash_prompt("Hello World", "hot", "month")
    assert h1 != h3


# 7. list_prompts respects limit and newest-first order
def test_list_prompts_limit(tmp_path: Path) -> None:
    db = tmp_path / "cache.db"
    now = datetime.now(timezone.utc)
    with Cache(db) as c:
        for i in range(3):
            row = _make_prompt_row(f"hash{i:04d}")
            ts = (now + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
            row = PromptRow(**{**row.model_dump(), "ran_at": ts, "prompt_hash": f"hash{i:04d}"})
            c.put_prompt(row)

        results = c.list_prompts(limit=2)

    assert len(results) == 2
    assert results[0].prompt_hash == "hash0002"
    assert results[1].prompt_hash == "hash0001"


# 8. stats returns expected shape
def test_stats(tmp_path: Path) -> None:
    db = tmp_path / "cache.db"
    with Cache(db) as c:
        c.put_post(_make_post())
        c.put_summary("abc123", "qwen3-coder:30b", _make_summary())
        c.put_prompt(_make_prompt_row())
        s = c.stats()

    assert "posts" in s
    assert "prompts" in s
    assert "summaries" in s
    assert "db_size_bytes" in s
    assert s["posts"] >= 1
    assert s["summaries"] >= 1
    assert s["prompts"] >= 1
    assert s["db_size_bytes"] > 0
