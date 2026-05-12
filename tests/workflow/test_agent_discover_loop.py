"""Workflow test for full discover loop."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from social_scraper.core.agent.discover import DiscoverConfig, run_discover
from social_scraper.core.schema import SourceKind


pytestmark = pytest.mark.workflow


class _FakeLLM:
    model = "fake"
    def json_call(self, system, user, model_cls):
        name = model_cls.__name__
        if name == "_Proposal":
            return model_cls(subreddits=["test"])
        if name == "_TopicArea":
            return model_cls(area="test_area", new=True)
        if name == "_RankedList":
            item_cls = model_cls.model_fields["ranked"].annotation.__args__[0]
            return model_cls(ranked=[item_cls(post_id="r0", relevance=0.7)])
        if name == "PostSummary":
            from social_scraper.core.schema import PostSummary
            return PostSummary(
                post_id="r0", source=SourceKind.reddit, summary="s",
                themes=["t"], relevance_to_prompt=0.7,
            )
        raise AssertionError(name)
    def chat_stream(self, system, user):
        yield "Narrative."
    def ping(self):
        return True


class _FakeReddit:
    def about_subreddit(self, name):
        return {"display_name": name, "subscribers": 5000, "subreddit_type": "public", "over18": False}
    def search_subreddits(self, q, limit=10):
        return []
    def fetch_listing(self, sub, listing="top", time_filter="month", limit=25):
        from social_scraper.core.schema import RawPost
        return [
            RawPost(source=SourceKind.reddit, id=f"r{i}", url="u", title=f"Trend {i}",
                    score=10 - i, num_comments=2, created_utc=1.0, subreddit=sub)
            for i in range(3)
        ], None
    def fetch_comments(self, sub, post_id, limit=10):
        from social_scraper.core.schema import RawPost
        return RawPost(source=SourceKind.reddit, id=post_id, url="u", title="t",
                       score=10, num_comments=2, created_utc=1.0, subreddit=sub)


class _FakeHN:
    def search(self, q, window_days=30, limit=50):
        return []


class _FakeIH:
    def fetch_listing(self, category, limit=20):
        return []


class _FakeTrends:
    _backend = None
    def snapshot(self, kw, window_days=30, geo=""):
        from social_scraper.core.sources.google_trends import TrendsResult
        return TrendsResult(keyword=kw, geo=geo, window_days=window_days,
                            interest_over_time={"dates": [], "values": {kw: []}},
                            top_related=[])


class _PickFirst:
    """Stand-in for the agent driver — picks the first N candidates."""
    def pick_topics(self, candidates, top_n):
        return candidates[:top_n]


def test_discover_writes_parent_run_with_children(tmp_path):
    cfg = DiscoverConfig(
        window_days=7, top_n=2,
        sources=[SourceKind.reddit, SourceKind.hn, SourceKind.indiehackers, SourceKind.google_trends],
        data_root=tmp_path / "data",
        cache_path=tmp_path / "cache" / "c.sqlite",
        reputation_path=tmp_path / "cache" / "rep.json",
    )
    result = run_discover(
        cfg, agent_driver=_PickFirst(),
        llm=_FakeLLM(), reddit=_FakeReddit(), hn=_FakeHN(),
        indiehackers=_FakeIH(), google_trends=_FakeTrends(),
        now=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )
    assert result["partial"] is False
    assert result["child_count"] == 2
    assert result["summary_path"].is_file()
