"""Tests for pipeline.summarize."""
from __future__ import annotations

import pytest

from social_scraper.core.llm.ollama import OllamaError
from social_scraper.core.pipeline.summarize import summarize_post
from social_scraper.core.schema import PostSummary, RawComment, RawPost, SourceKind


pytestmark = pytest.mark.component


def _post() -> RawPost:
    return RawPost(
        source=SourceKind.reddit, id="abc", url="u", title="Hello",
        body="A useful long-ish body" * 5, score=10, num_comments=2,
        created_utc=1.0, subreddit="x",
        top_comments=[RawComment(id="c1", body="great", score=3, created_utc=2.0)],
    )


class _StubLLM:
    def __init__(self, fail: bool = False):
        self._fail = fail

    def json_call(self, system, user, model_cls):
        if self._fail:
            raise OllamaError("nope")
        return model_cls(
            post_id="abc",
            source=SourceKind.reddit,
            summary="A summary",
            themes=["t1"],
            relevance_to_prompt=0.5,
        )


def test_summarize_happy_path():
    summary, fallback = summarize_post(_StubLLM(), "prompt", _post(), relevance=0.5)
    assert isinstance(summary, PostSummary)
    assert summary.summary == "A summary"
    assert fallback is False


def test_summarize_fallback_on_llm_error():
    summary, fallback = summarize_post(_StubLLM(fail=True), "prompt", _post(), relevance=0.5)
    assert fallback is True
    assert summary.post_id == "abc"
    assert summary.summary  # extracted truncated text
