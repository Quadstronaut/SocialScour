"""Tests for individual agent tool functions."""
from __future__ import annotations

import pytest

from social_scraper.core.agent.discover import (
    _tool_top_trending_hn,
    _tool_top_trending_reddit,
)


pytestmark = pytest.mark.component


class _FakeReddit:
    def fetch_listing(self, sub, listing, time_filter, limit):
        from social_scraper.core.schema import RawPost, SourceKind
        posts = [
            RawPost(source=SourceKind.reddit, id=f"r{i}", url="u",
                    title=f"Trending topic {i}", score=100 - i, num_comments=10,
                    created_utc=1.0, subreddit="popular")
            for i in range(3)
        ]
        return posts, None


class _FakeHN:
    def search(self, query, window_days, limit):
        from social_scraper.core.schema import RawPost, SourceKind
        return [
            RawPost(source=SourceKind.hn, id=f"story:h{i}", url="u",
                    title=f"HN trend {i}", score=50 - i, num_comments=5,
                    created_utc=1.0)
            for i in range(3)
        ]


def test_top_trending_reddit_returns_titles():
    out = _tool_top_trending_reddit(_FakeReddit(), window_days=7, limit=2)
    assert len(out) == 2
    assert all(isinstance(t, str) for t in out)
    assert "Trending topic" in out[0]


def test_top_trending_hn_returns_titles():
    out = _tool_top_trending_hn(_FakeHN(), window_days=7, limit=2)
    assert len(out) == 2
    assert "HN trend" in out[0]
