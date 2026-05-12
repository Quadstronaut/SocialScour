"""Tests for IndieHackersClient (BeautifulSoup listing parse)."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from social_scraper.core.schema import SourceKind
from social_scraper.core.sources.indiehackers import IndieHackersClient


pytestmark = pytest.mark.component
FIX = Path(__file__).parent / "fixtures" / "indiehackers"


def test_fetch_listing_parses_two_items():
    html = (FIX / "listing.html").read_text()

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = IndieHackersClient(http_client=http, throttle_s=0.0)
    posts = client.fetch_listing("ideas-and-validation", limit=10)
    assert len(posts) == 2
    assert {p.source for p in posts} == {SourceKind.indiehackers}
    assert posts[0].title.startswith("Vibecoding")
    assert posts[0].score == 23
