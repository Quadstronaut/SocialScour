"""Tests for pydantic models in social_scraper.core.schema."""
from __future__ import annotations

import pytest

from social_scraper.core.schema import (
    Digest,
    PostSummary,
    RawComment,
    RawPost,
    RunMeta,
    SourceKind,
)


pytestmark = pytest.mark.component


def test_source_kind_values():
    assert {s.value for s in SourceKind} == {"reddit", "hn", "indiehackers", "google_trends"}


def test_raw_post_roundtrip():
    post = RawPost(
        source=SourceKind.reddit,
        id="abc",
        url="https://example.com/abc",
        title="hello",
        author="user1",
        body="body text",
        score=42,
        num_comments=5,
        created_utc=1700000000.0,
        subreddit="test",
    )
    data = post.model_dump()
    assert RawPost.model_validate(data) == post


def test_raw_comment_defaults():
    c = RawComment(id="x", body="hi", score=1, created_utc=1.0)
    assert c.author is None
    assert c.depth == 0


def test_post_summary_relevance_bounds():
    with pytest.raises(ValueError):
        PostSummary(
            post_id="x",
            source=SourceKind.reddit,
            summary="s",
            themes=["t"],
            relevance_to_prompt=1.5,
        )


def test_digest_minimum():
    d = Digest(
        prompt="x",
        generated_utc="2026-05-11T00:00:00Z",
        sources_used=[SourceKind.reddit],
        item_count=0,
        themes=[],
        narrative="",
    )
    assert d.item_count == 0


def test_run_meta_warnings_default_empty():
    m = RunMeta(
        topic="x",
        slug="x",
        window_days=30,
        sources=[SourceKind.reddit],
        model="qwen3-coder:30b",
        summarizer="ollama",
        started_utc="2026-05-11T00:00:00Z",
    )
    assert m.warnings == []
    assert m.finished_utc is None
