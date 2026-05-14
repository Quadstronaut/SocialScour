"""Tests for pipeline.rank (embeddings ranker + deterministic fallback)."""
from __future__ import annotations

import math
import pytest

from social_scraper.core.llm.ollama import OllamaError
from social_scraper.core.pipeline.rank import RankingResult, rank_posts
from social_scraper.core.schema import RawPost, SourceKind


pytestmark = pytest.mark.component


def _post(pid: str, title: str = "", body: str = "", score: int = 0,
          comments: int = 0, source: SourceKind = SourceKind.reddit) -> RawPost:
    return RawPost(
        source=source, id=pid, url="u", title=title or pid, body=body,
        score=score, num_comments=comments, created_utc=1.0,
        subreddit="x" if source == SourceKind.reddit else None,
    )


class _FixedEmbedder:
    """Embedder that returns pre-canned vectors keyed by exact text-prefix match."""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def embed(self, texts, model=None):
        out: list[list[float]] = []
        for t in texts:
            matched = None
            for key, vec in self._vectors.items():
                if t.startswith(key):
                    matched = vec
                    break
            out.append(matched if matched is not None else [0.0, 0.0, 0.0])
        return out


class _FailingEmbedder:
    def embed(self, texts, model=None):
        raise OllamaError("forced")


def test_rank_relevant_post_scores_higher_than_irrelevant():
    """Known-relevant post must outrank known-irrelevant on cosine similarity."""
    embedder = _FixedEmbedder({
        "TOPIC": [1.0, 0.0, 0.0],
        "Lynis audit tool for Linux hardening": [0.99, 0.1, 0.0],
        "Happy Birthday, Linus Torvalds": [0.0, 1.0, 0.0],
    })
    posts = [
        _post("good", title="Lynis audit tool for Linux hardening"),
        _post("bad", title="Happy Birthday, Linus Torvalds"),
    ]
    result = rank_posts(
        embedder, "TOPIC", posts,
        top_k=10, drop_threshold=0.5,
    )
    assert isinstance(result, RankingResult)
    assert result.used_fallback is False
    # Higher cosine sim should rank first.
    assert result.ranked[0][0].id == "good"
    assert result.ranked[1][0].id == "bad"
    assert result.ranked[0][1] > result.ranked[1][1]


def test_rank_drop_threshold_filters_low_relevance():
    embedder = _FixedEmbedder({
        "TOPIC": [1.0, 0.0],
        "relevant": [0.95, 0.1],
        "noise": [0.0, 1.0],
    })
    posts = [_post("rel", title="relevant"), _post("noise", title="noise")]
    result = rank_posts(embedder, "TOPIC", posts, top_k=10, drop_threshold=0.5)
    kept_ids = [p.id for p, _, _ in result.kept]
    dropped_ids = [p.id for p, _, _ in result.dropped]
    assert "rel" in kept_ids
    assert "noise" in dropped_ids


def test_rank_top_k_caps_kept():
    embedder = _FixedEmbedder({
        "TOPIC": [1.0, 0.0],
        **{f"post-{i}": [1.0, 0.0] for i in range(10)},
    })
    posts = [_post(f"p{i}", title=f"post-{i}") for i in range(10)]
    result = rank_posts(embedder, "TOPIC", posts, top_k=3, drop_threshold=0.0)
    assert len(result.kept) == 3
    # All 10 should still appear in ranked (full list).
    assert len(result.ranked) == 10


def test_rank_reason_records_score_and_method():
    embedder = _FixedEmbedder({"TOPIC": [1.0, 0.0], "p": [1.0, 0.0]})
    posts = [_post("p1", title="p")]
    result = rank_posts(embedder, "TOPIC", posts, top_k=1, drop_threshold=0.0)
    _, _, reason = result.ranked[0]
    assert "cosine" in reason.lower() or "embed" in reason.lower()


def test_rank_falls_back_on_embedder_failure():
    posts = [_post("a", score=10, comments=5), _post("b", score=100, comments=1)]
    result = rank_posts(_FailingEmbedder(), "prompt", posts, top_k=2, drop_threshold=0.0)
    assert result.used_fallback is True
    # Fallback: sort by score+num_comments desc → b first.
    assert result.ranked[0][0].id == "b"


def test_rank_empty_input():
    result = rank_posts(_FailingEmbedder(), "prompt", [], top_k=5, drop_threshold=0.0)
    assert result.ranked == []
    assert result.kept == []
    assert result.used_fallback is False
