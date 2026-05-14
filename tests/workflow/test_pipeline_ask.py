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
        if name == "PostSummary":
            return PostSummary(
                post_id="abc", source=SourceKind.reddit,
                summary="A summary.", themes=["t"], relevance_to_prompt=0.9,
            )
        if name == "TopicConfidence":
            return model_cls(addressed=True, confidence=0.9, rationale="fake")
        raise AssertionError(f"unexpected schema {name}")

    def chat_stream(self, system, user):
        yield "The narrative."

    def ping(self):
        return True

    def embed(self, texts, model=None):
        # Return identical unit vectors so cosine sim = 1.0 for every post.
        return [[1.0, 0.0, 0.0] for _ in texts]


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
        min_kept_for_summary=1,  # the fake yields exactly one post
        drop_threshold=0.0,
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


class _TrackingReddit(_FakeReddit):
    def __init__(self) -> None:
        self.about_calls: list[str] = []
        self.search_calls: list[str] = []
        self.listing_calls: list[str] = []

    def about_subreddit(self, name):
        self.about_calls.append(name)
        return super().about_subreddit(name)

    def search_subreddits(self, query, limit=10):
        self.search_calls.append(query)
        return super().search_subreddits(query, limit=limit)

    def fetch_listing(self, sub, listing="top", time_filter="month", limit=25):
        self.listing_calls.append(sub)
        return super().fetch_listing(sub, listing=listing, time_filter=time_filter, limit=limit)


class _DiscoveryShouldNotRunLLM(_FakeLLM):
    """Same as _FakeLLM but raises if discover_subs JSON contracts are invoked."""

    def json_call(self, system, user, model_cls):
        name = model_cls.__name__
        if name in {"_Proposal", "_TopicArea"}:
            raise AssertionError(
                f"discover_subreddits called unexpectedly (schema {name})"
            )
        return super().json_call(system, user, model_cls)


class _LowRelevanceLLM(_FakeLLM):
    """Same as _FakeLLM but embeds all posts as orthogonal to the topic vector."""

    def embed(self, texts, model=None):
        # First text is the topic; remaining are posts. Orthogonal => cosine = 0.
        out: list[list[float]] = []
        for i, _ in enumerate(texts):
            out.append([1.0, 0.0, 0.0] if i == 0 else [0.0, 1.0, 0.0])
        return out


class _MultiPostReddit(_FakeReddit):
    """Returns N posts per listing call so kept_ratio math is meaningful."""

    def fetch_listing(self, sub, listing="top", time_filter="month", limit=25):
        posts = []
        for i in range(10):
            posts.append(RawPost(
                source=SourceKind.reddit, id=f"p{i}", url="u",
                title=f"Off topic {i}", body="x", score=i, num_comments=1,
                created_utc=1.0, subreddit=sub,
            ))
        return posts, None


def test_ask_off_topic_corpus_raises_topic_mismatch(tmp_path):
    """If too few posts cleared the relevance threshold, skip summarization."""
    cfg = AskConfig(
        topic="Linux server hardening",
        window_days=30,
        sources=[SourceKind.reddit],
        subreddits=["random"],
        model="fake",
        summarizer="ollama",
        data_root=tmp_path / "data",
        cache_path=tmp_path / "cache" / "c.sqlite",
        reputation_path=tmp_path / "cache" / "rep.json",
        drop_threshold=0.55,
        min_kept_for_summary=5,
    )
    result = run_ask(
        cfg,
        llm=_LowRelevanceLLM(),
        reddit=_MultiPostReddit(),
        hn=_FakeHN(),
        indiehackers=_FakeIH(),
        google_trends=_FakeTrends(),
        now=datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert result["topic_mismatch"] is True
    summary = (result["run_dir"] / "summary" / "summary.md").read_text()
    assert "topic_mismatch" in summary

    import json
    meta = json.loads((result["run_dir"] / "meta.json").read_text())
    assert meta["topic_mismatch"] is True
    assert any("topic_mismatch" in w for w in meta["warnings"])
    # Per-source stats wired through:
    assert "reddit" in meta["per_source_stats"]
    stats = meta["per_source_stats"]["reddit"]
    assert stats["discovered"] == 10
    assert stats["kept"] == 0
    assert stats["dropped"] == 10


def test_ask_summary_has_topic_confidence_header(tmp_path):
    """Successful runs prepend a topic-confidence line to summary.md."""
    cfg = AskConfig(
        topic="vibecoding",
        window_days=30,
        sources=[SourceKind.reddit],
        model="fake",
        summarizer="ollama",
        data_root=tmp_path / "data",
        cache_path=tmp_path / "cache" / "c.sqlite",
        reputation_path=tmp_path / "cache" / "rep.json",
        min_kept_for_summary=1,
        drop_threshold=0.0,
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
    summary = (result["run_dir"] / "summary" / "summary.md").read_text()
    assert "topic-confidence" in summary
    assert result["topic_confidence"]["addressed"] is True


def test_ask_with_pinned_subreddits_skips_discovery(tmp_path):
    """When AskConfig.subreddits is set, discover_subreddits is not invoked."""
    reddit = _TrackingReddit()
    cfg = AskConfig(
        topic="linux server hardening",
        window_days=30,
        sources=[SourceKind.reddit],
        subreddits=["sysadmin", "selfhosted"],
        model="fake",
        summarizer="ollama",
        data_root=tmp_path / "data",
        cache_path=tmp_path / "cache" / "c.sqlite",
        reputation_path=tmp_path / "cache" / "rep.json",
    )
    run_ask(
        cfg,
        llm=_DiscoveryShouldNotRunLLM(),
        reddit=reddit,
        hn=_FakeHN(),
        indiehackers=_FakeIH(),
        google_trends=_FakeTrends(),
        now=datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc),
    )
    # Discovery probes are skipped entirely:
    assert reddit.about_calls == []
    assert reddit.search_calls == []
    # But the pinned subs are fetched verbatim:
    assert reddit.listing_calls == ["sysadmin", "selfhosted"]
