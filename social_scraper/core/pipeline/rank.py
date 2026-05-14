"""Embeddings-based relevance ranker (bge-m3 cosine similarity + deterministic fallback)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from social_scraper.core.llm.ollama import OllamaError
from social_scraper.core.schema import RawPost


# How much body text we feed into the embedding alongside the title.
_BODY_PREFIX = 200


@dataclass
class RankingResult:
    """Output of rank_posts.

    `ranked` is the full input sorted desc by relevance (post, score, reason).
    `kept` are the top_k items whose relevance >= drop_threshold.
    `dropped` are the rest (below threshold or below the top_k cutoff).
    """

    ranked: list[tuple[RawPost, float, str]] = field(default_factory=list)
    drop_threshold: float = 0.55
    top_k: int = 15
    used_fallback: bool = False

    @property
    def kept(self) -> list[tuple[RawPost, float, str]]:
        return [t for t in self.ranked[: self.top_k] if t[1] >= self.drop_threshold]

    @property
    def dropped(self) -> list[tuple[RawPost, float, str]]:
        kept_ids = {p.id for p, _, _ in self.kept}
        return [t for t in self.ranked if t[0].id not in kept_ids]


def _post_text(p: RawPost) -> str:
    body = (p.body or "")[:_BODY_PREFIX]
    return f"{p.title}\n\n{body}" if body else p.title


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _fallback(posts: list[RawPost], top_k: int, drop_threshold: float) -> RankingResult:
    scored = [
        (p, 0.0, "embed_fallback:no-embedding (sorted by score+comments)")
        for p in posts
    ]
    scored.sort(key=lambda t: (t[0].score + t[0].num_comments), reverse=True)
    return RankingResult(
        ranked=scored,
        drop_threshold=drop_threshold,
        top_k=top_k,
        used_fallback=True,
    )


def rank_posts(
    embedder,
    prompt: str,
    posts: list[RawPost],
    *,
    top_k: int = 15,
    drop_threshold: float = 0.55,
) -> RankingResult:
    """Rank posts by cosine similarity between prompt and `title + body[:200]`.

    `embedder` must expose `embed(texts: list[str]) -> list[list[float]]`.
    On embedder failure, falls back to score+num_comments sorting with relevance=0.
    """
    if not posts:
        return RankingResult(drop_threshold=drop_threshold, top_k=top_k)

    texts = [prompt] + [_post_text(p) for p in posts]
    try:
        vectors = embedder.embed(texts)
    except OllamaError:
        return _fallback(posts, top_k, drop_threshold)

    if not vectors or len(vectors) != len(texts):
        return _fallback(posts, top_k, drop_threshold)

    prompt_vec = vectors[0]
    post_vecs = vectors[1:]

    scored: list[tuple[RawPost, float, str]] = []
    for post, vec in zip(posts, post_vecs):
        sim = _cosine(prompt_vec, vec)
        reason = f"cosine={sim:.3f} (bge-m3 embed of title+body[:200])"
        scored.append((post, sim, reason))

    # Sort by cosine desc, with raw engagement as a tiebreaker for ties.
    scored.sort(key=lambda t: (t[1], t[0].score, t[0].num_comments), reverse=True)
    return RankingResult(
        ranked=scored,
        drop_threshold=drop_threshold,
        top_k=top_k,
        used_fallback=False,
    )
