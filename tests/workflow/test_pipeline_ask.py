"""Workflow test for pipeline.ask — full pipeline against fakes."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from social_scraper.core.pipeline.ask import AskConfig, run_ask
from social_scraper.core.schema import (
    PostSummary,
    RawComment,
    RawPost,
    SourceKind,
)


pytestmark = pytest.mark.workflow


class _FakeLLM:
    """LLM that satisfies discover_subs, rank, summarize, and narrate contracts."""

    def __init__(self) -> None:
        self.model = "fake"

    def json_call(self, system, user, model_cls):
        name = model_cls.__name__
        if name == "_Proposal":
            return model_cls(subreddits=["test"])
        if name == "_TopicArea":
            return model_cls(area="test_area", new=True)
        if name == "_RankedList":
            item_cls = model_cls.model_fields["ranked"].annotation.__args__[0]
            return model_cls(ranked=[item_cls(post_id="abc", relevance=0.9)])
        if name == "PostSummary":
            return PostSummary(
                post_id="abc", source=SourceKind.reddit,
                summary="A summary.", themes=["t"], relevance_to_prompt=0.9,
            )
        raise AssertionError(f"unexpected schema {name}")

    def chat_stream(self, system, user):
        yield "The narrative."

    def ping(self):
        return True


class _FakeReddit:
    def about_subreddit(self, name):
        return {"display_name": name, "subscribers": 5000, "subreddit_type": "public", "over18": False}

    def search_subreddits(self, query, limit=10):
        return []

    def fetch_listing(self, sub, listing="top", time_filter="month", limit=25):
        post = RawPost(
            source=SourceKind.reddit, id="abc", url="u", title="t",
            body="b", score=10, num_comments=2, created_utc=1.0, subreddit="test",
        )
        return [post], None

    def fetch_comments(self, sub, post_id, limit=10):
        post = RawPost(
            source=SourceKind.reddit, id="abc", url="u", title="t",
            body="b", score=10, num_comments=2, created_utc=1.0, subreddit="test",
            top_comments=[RawComment(id="c1", body="great", score=2, created_utc=2.0)],
        )
        return post


class _FakeHN:
    def search(self, query, window_days=30, limit=50):
        return []


class _FakeIH:
    def fetch_listing(self, category, limit=20):
        return []


class _FakeTrends:
    def snapshot(self, keyword, window_days=30, geo=""):
        from social_scraper.core.sources.google_trends import TrendsResult
        return TrendsResult(
            keyword=keyword, geo=geo, window_days=window_days,
            interest_over_time={"dates": [], "values": {keyword: []}},
            top_related=[],
        )


def test_ask_writes_full_run_layout(tmp_path):
    cfg = AskConfig(
        topic="vibecoding",
        window_days=30,
        sources=[SourceKind.reddit, SourceKind.hn, SourceKind.indiehackers, SourceKind.google_trends],
        model="fake",
        summarizer="ollama",
        data_root=tmp_path / "data",
        cache_path=tmp_path / "cache" / "c.sqlite",
        reputation_path=tmp_path / "cache" / "rep.json",
    )
    result = run_ask(
        cfg,
        llm=_FakeLLM(),
        reddit=_FakeReddit(),
        hn=_FakeHN(),
        indiehackers=_FakeIH(),
        google_trends=_FakeTrends(),
        now=datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc),
    )
    run_dir: Path = result["run_dir"]
    assert run_dir.is_dir()
    assert (run_dir / "summary" / "summary.md").is_file()
    assert (run_dir / "raw" / "reddit.jsonl").is_file()
    assert (run_dir / "meta.json").is_file()
    timeline = tmp_path / "data" / "topics" / "vibecoding" / "timeline.md"
    assert timeline.is_file()
    assert "# vibecoding" in timeline.read_text()
