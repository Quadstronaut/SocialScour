"""Tests for HNClient (Algolia search)."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from social_scraper.core.schema import SourceKind
from social_scraper.core.sources.hn import HNClient


pytestmark = pytest.mark.component
FIX = Path(__file__).parent / "fixtures" / "hn"


def test_search_parses_stories_and_comments():
    payload = json.loads((FIX / "algolia_search.json").read_text())

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = HNClient(http_client=http)
    posts = client.search("vibecoding", window_days=30, limit=20)
    assert len(posts) == 2
    assert {p.source for p in posts} == {SourceKind.hn}
    story = next(p for p in posts if "Show HN" in p.title)
    assert story.score == 42
