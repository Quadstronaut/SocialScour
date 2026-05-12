"""Tests for pipeline.discover_subs."""
from __future__ import annotations

import httpx
import pytest

from social_scraper.core.pipeline.discover_subs import discover_subreddits
from social_scraper.core.sources.reddit import RedditClient


pytestmark = pytest.mark.component


class _FakeLLM:
    def __init__(self, sub_names: list[str], area: str = "test_area") -> None:
        self._sub_names = sub_names
        self._area = area

    def json_call(self, system, user, model_cls):
        if "area" in model_cls.model_fields:
            return model_cls(area=self._area, new=True)
        return model_cls(subreddits=self._sub_names)


def _reddit_with_about_subs(approved: dict[str, dict]) -> RedditClient:
    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if "subreddits/search.json" in url:
            return httpx.Response(200, json={"data": {"children": []}})
        for name, data in approved.items():
            if f"/r/{name}/about.json" in url:
                return httpx.Response(200, json={"data": data})
        return httpx.Response(404, json={})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return RedditClient(http, min_interval=0.0, jitter=0.0)


def test_discover_filters_below_min_subs():
    llm = _FakeLLM(["BigSub", "TinySub"])
    reddit = _reddit_with_about_subs({
        "BigSub": {"display_name": "BigSub", "subscribers": 5000, "subreddit_type": "public", "over18": False},
        "TinySub": {"display_name": "TinySub", "subscribers": 100, "subreddit_type": "public", "over18": False},
    })
    subs, area = discover_subreddits(llm, reddit, "prompt", reputation={"topic_areas": {}}, max_subs=5)
    assert "BigSub" in subs
    assert "TinySub" not in subs
