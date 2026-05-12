"""Deterministic offline tests for render.py and reputation.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from reddit_research.render import append_jsonl, slugify, write_json, write_markdown
from reddit_research.reputation import Reputation
from reddit_research.schema import (
    Digest,
    NotablePost,
    PostSummary,
    RawPost,
    SentimentJsonlRow,
    SubSentiment,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _post(pid: str, sub: str = "homelab", score: int = 100) -> RawPost:
    return RawPost(
        id=pid,
        subreddit=sub,
        title=f"Post {pid}",
        url=f"https://reddit.com/r/{sub}/{pid}",
        permalink=f"https://reddit.com/r/{sub}/comments/{pid}/",
        selftext="Some body text",
        score=score,
        created_utc=1_700_000_000.0,
    )


def _summary(pid: str, relevance: float = 0.8, topics: list[str] | None = None) -> PostSummary:
    return PostSummary(
        post_id=pid,
        one_sentence="Routers matter for home security.",
        three_bullets=["Use WPA3", "Segment IoT", "Update firmware"],
        key_quotes=["Always patch your router"],
        sentiment="positive",
        topics=topics or ["security", "networking"],
        relevance_to_prompt=relevance,
    )


def _sentiment(sub: str) -> SubSentiment:
    return SubSentiment(
        subreddit=sub,
        score=0.7,
        confidence=0.8,
        n_posts=3,
        n_comments=20,
        theme="Security is top concern",
    )


def _digest(posts_by_id: dict[str, RawPost]) -> Digest:
    pid = next(iter(posts_by_id))
    post = posts_by_id[pid]
    return Digest(
        prompt="How do people secure home networks",
        generated_utc="2026-05-11T12:00:00Z",
        subreddits_used=[post.subreddit],
        post_count=1,
        themes=["security", "networking"],
        narrative="Reddit users emphasise patching routers and using WPA3.",
        notable_posts=[NotablePost(post_id=pid, why_notable=f"r/{post.subreddit}, score {post.score}")],
        per_sub_sentiment=[_sentiment(post.subreddit)],
    )


# ---------------------------------------------------------------------------
# Test 1 — slugify
# ---------------------------------------------------------------------------

def test_slugify_normalises_prompt():
    result = slugify("How do people SECURE home networks???")
    assert result == "how-do-people-secure-home-networks"


# ---------------------------------------------------------------------------
# Test 2 — write_markdown sections present
# ---------------------------------------------------------------------------

def test_write_markdown_sections(tmp_path: Path):
    post = _post("abc123")
    summary = _summary("abc123")
    digest = _digest({"abc123": post})
    out = tmp_path / "out.md"
    write_markdown(out, digest, {"abc123": post}, {"abc123": summary})
    text = out.read_text(encoding="utf-8")
    assert "# How do people secure home networks" in text
    assert "**Themes:**" in text
    assert "**Subreddits used:**" in text
    assert "## Notable posts" in text
    assert "## Per-subreddit sentiment" in text


# ---------------------------------------------------------------------------
# Test 3 — write_json keys present
# ---------------------------------------------------------------------------

def test_write_json_structure(tmp_path: Path):
    post = _post("xyz99")
    summary = _summary("xyz99")
    digest = _digest({"xyz99": post})
    out = tmp_path / "out.json"
    write_json(out, digest, {"xyz99": post}, {"xyz99": summary})
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "meta" in data
    assert "digest" in data
    assert "posts" in data


# ---------------------------------------------------------------------------
# Test 4 — append_jsonl accumulates rows
# ---------------------------------------------------------------------------

def test_append_jsonl_two_calls(tmp_path: Path):
    path = tmp_path / "tickers" / "NVDA.jsonl"

    def _row(sub: str) -> SentimentJsonlRow:
        return SentimentJsonlRow(
            ts="2026-05-11T13:00:00Z",
            ticker="NVDA",
            sub=sub,
            score=0.5,
            confidence=0.7,
            n_posts=5,
            n_comments=50,
            theme="AI strong",
            prompt="NVDA outlook",
            model="qwen3-coder:30b",
        )

    append_jsonl(path, [_row("wallstreetbets")])
    append_jsonl(path, [_row("investing")])

    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    for line in lines:
        parsed = json.loads(line)
        SentimentJsonlRow(**parsed)


# ---------------------------------------------------------------------------
# Test 5 — Reputation creates file on load and persists
# ---------------------------------------------------------------------------

def test_reputation_fresh_file_and_persist(tmp_path: Path):
    rep_path = tmp_path / "cache" / "reputation.json"
    rep = Reputation(rep_path)

    data = rep.load()
    assert data == {"version": 1, "topic_areas": {}}
    assert not rep_path.exists()

    rep.promote("encryption", "netsec")
    rep.save()

    assert rep_path.exists()

    rep2 = Reputation(rep_path)
    rep2.load()
    assert "netsec" in rep2.promoted_subs("encryption")


# ---------------------------------------------------------------------------
# Test 6 — auto_update increment / decrement / promoted exempt
# ---------------------------------------------------------------------------

def test_auto_update_scoring(tmp_path: Path):
    rep = Reputation(tmp_path / "rep.json")
    rep.load()

    rep.promote("home_networking", "netsec")

    signals = {
        "homelab":    {"signal_density": 0.75, "n_posts": 5},
        "lowsignal":  {"signal_density": 0.10, "n_posts": 4},
        "netsec":     {"signal_density": 0.05, "n_posts": 6},
    }
    changes = rep.auto_update("home_networking", signals)

    area_subs = rep._data["topic_areas"]["home_networking"]["subs"]

    assert area_subs["homelab"]["score"] == 1
    assert area_subs["lowsignal"]["score"] == -1
    assert area_subs["netsec"]["score"] == 0

    assert "homelab" in changes
    assert "lowsignal" in changes
    assert "netsec" not in changes


# ---------------------------------------------------------------------------
# Test 7 — top_reputed and promoted_subs
# ---------------------------------------------------------------------------

def test_top_reputed_and_promoted(tmp_path: Path):
    rep = Reputation(tmp_path / "rep.json")
    rep.load()

    area = "encryption"
    rep._data.setdefault("topic_areas", {})[area] = {
        "subs": {
            "crypto":   {"score": 7, "last_useful_utc": "2026-04-01T00:00:00Z", "promoted": False},
            "netsec":   {"score": 4, "last_useful_utc": "2026-04-22T00:00:00Z", "promoted": True},
            "privacy":  {"score": 9, "last_useful_utc": "2026-05-01T00:00:00Z", "promoted": False},
            "lowrep":   {"score": 1, "last_useful_utc": "2026-01-01T00:00:00Z", "promoted": False},
        }
    }

    top3 = rep.top_reputed(area, n=3)
    assert top3 == ["privacy", "crypto", "netsec"]

    promoted = rep.promoted_subs(area)
    assert "netsec" in promoted
    assert len(promoted) == 1
