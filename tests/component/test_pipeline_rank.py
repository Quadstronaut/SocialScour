"""Tests for pipeline.rank with strict JSON + fallback."""
from __future__ import annotations

import pytest

from social_scraper.core.llm.ollama import OllamaError
from social_scraper.core.pipeline.rank import rank_posts
from social_scraper.core.schema import RawPost, SourceKind


pytestmark = pytest.mark.component


def _post(pid: str, score: int, comments: int = 0) -> RawPost:
    return RawPost(
        source=SourceKind.reddit, id=pid, url="u", title=pid,
        score=score, num_comments=comments, created_utc=1.0, subreddit="x",
    )


class _StubLLM:
    def __init__(self, ranked: dict[str, float] | None = None, raise_on_call: bool = False):
        self._ranked = ranked
        self._raise = raise_on_call

    def json_call(self, system, user, model_cls):
        if self._raise:
            raise OllamaError("forced")
        ranked_field = model_cls.model_fields["ranked"]
        item_cls = ranked_field.annotation.__args__[0]
        items = [item_cls(post_id=pid, relevance=rel) for pid, rel in self._ranked.items()]
        return model_cls(ranked=items)


def test_rank_orders_by_llm_then_native_score():
    posts = [_post("a", score=10), _post("b", score=100), _post("c", score=5)]
    llm = _StubLLM({"a": 0.9, "b": 0.1, "c": 0.9})
    ranked, used_fallback = rank_posts(llm, "prompt", posts, top_k=3)
    assert used_fallback is False
    # a and c both 0.9 → a (score 10) before c (score 5); b last.
    ids = [p.id for p, _ in ranked]
    assert ids == ["a", "c", "b"]


def test_rank_falls_back_on_ollama_error():
    posts = [_post("a", score=10, comments=5), _post("b", score=100, comments=1)]
    llm = _StubLLM(raise_on_call=True)
    ranked, used_fallback = rank_posts(llm, "prompt", posts, top_k=2)
    assert used_fallback is True
    # Fallback: sort by score + num_comments desc → b first.
    assert ranked[0][0].id == "b"


def test_rank_top_k_limits_output():
    posts = [_post(f"p{i}", score=i) for i in range(10)]
    llm = _StubLLM({f"p{i}": float(i) / 10 for i in range(10)})
    ranked, _ = rank_posts(llm, "prompt", posts, top_k=3)
    assert len(ranked) == 3
