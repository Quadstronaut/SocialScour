"""Offline tests for fetch.py — no real HTTP calls."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from reddit_research.fetch import RedditBlockedError, RedditClient

FIXTURES = Path(__file__).parent / "fixtures"


def _mock_response(status: int = 200, body: str | None = None, json_data=None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    if json_data is not None:
        resp.text = json.dumps(json_data)
        resp.json.return_value = json_data
    else:
        resp.text = body or ""
        try:
            resp.json.return_value = json.loads(body) if body else {}
        except (json.JSONDecodeError, TypeError):
            resp.json.side_effect = ValueError("not JSON")
    if status >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status}",
            request=MagicMock(),
            response=resp,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def _client(json_data=None, status: int = 200, body: str | None = None) -> tuple[RedditClient, MagicMock]:
    mock_http = MagicMock(spec=httpx.Client)
    resp = _mock_response(status=status, body=body, json_data=json_data)
    mock_http.get.return_value = resp
    rc = RedditClient(mock_http, "test-ua/0.1", min_interval=0.0, jitter=0.0)
    return rc, mock_http


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_blocked_on_403():
    rc, _ = _client(status=403)
    with pytest.raises(RedditBlockedError):
        rc.fetch_listing("test")


def test_blocked_on_html_body():
    html = "<html><body>Access denied</body></html>"
    rc, _ = _client(body=html)
    with pytest.raises(RedditBlockedError):
        rc.fetch_listing("test")


def test_fetch_listing_parses_fixture():
    data = _load("listing_r_test.json")
    rc, _ = _client(json_data=data)
    posts, cursor = rc.fetch_listing("test")
    assert len(posts) == 5
    assert posts[0].title == "How I segmented my home network with VLANs"
    assert posts[0].permalink.startswith("https://")
    assert cursor is None


def test_fetch_comments_parses_fixture():
    data = _load("comments_r_test.json")
    rc, _ = _client(json_data=data)
    post = rc.fetch_comments("test", "abc1")
    assert len(post.top_comments) == 8
    scores = [c.score for c in post.top_comments]
    assert scores == sorted(scores, reverse=True)


def test_search_subreddits_returns_three():
    data = _load("subreddit_search.json")
    rc, _ = _client(json_data=data)
    results = rc.search_subreddits("home network security")
    assert len(results) == 3
    assert results[0]["display_name"] == "homelab"


def test_about_subreddit_returns_none_on_404():
    rc, _ = _client(status=404)
    result = rc.about_subreddit("nonexistent")
    assert result is None
