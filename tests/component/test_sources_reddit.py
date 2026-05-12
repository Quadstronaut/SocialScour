"""Tests for RedditClient (ported)."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from social_scraper.core.schema import SourceKind
from social_scraper.core.sources.reddit import RedditClient


pytestmark = pytest.mark.component
FIX = Path(__file__).parent / "fixtures" / "reddit"


def _client_with(responses: dict[str, dict]) -> RedditClient:
    def handler(req: httpx.Request) -> httpx.Response:
        for key, payload in responses.items():
            if key in str(req.url):
                return httpx.Response(200, json=payload)
        return httpx.Response(404, json={})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return RedditClient(http, min_interval=0.0, jitter=0.0)


def test_search_subreddits_parses_fixture():
    data = json.loads((FIX / "subreddit_search.json").read_text())
    client = _client_with({"subreddits/search.json": data})
    results = client.search_subreddits("test", limit=5)
    assert isinstance(results, list)
    assert all("display_name" in r for r in results)


def test_about_subreddit_returns_data_or_none():
    data = json.loads((FIX / "subreddit_about.json").read_text())
    client = _client_with({"/about.json": data})
    out = client.about_subreddit("test")
    assert out is not None
    assert out.get("display_name") is not None


def test_fetch_listing_returns_rawposts():
    data = json.loads((FIX / "listing_r_test.json").read_text())
    client = _client_with({"top.json": data})
    posts, after = client.fetch_listing("test", listing="top", time_filter="month", limit=5)
    assert all(p.source == SourceKind.reddit for p in posts)
    assert all(p.subreddit for p in posts)


def test_fetch_comments_attaches_top_comments():
    data = json.loads((FIX / "comments_r_test.json").read_text())
    client = _client_with({"comments/": data})
    post = client.fetch_comments("test", "abc", limit=3)
    assert post.source == SourceKind.reddit
    assert isinstance(post.top_comments, list)
