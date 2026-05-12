"""LLM relevance ranker (strict-JSON Ollama mode + deterministic fallback)."""
from __future__ import annotations

import json

from pydantic import BaseModel

from social_scraper.core.llm.ollama import OllamaError
from social_scraper.core.schema import RawPost


_RANKER_SYSTEM = (
    "You are a relevance ranker. Given a research prompt and a list of post candidates, "
    "score each candidate's relevance to the prompt on a 0.0–1.0 scale."
)


class _RankItem(BaseModel):
    post_id: str
    relevance: float


class _RankedList(BaseModel):
    ranked: list[_RankItem]


def rank_posts(
    llm,
    prompt: str,
    posts: list[RawPost],
    top_k: int = 15,
) -> tuple[list[tuple[RawPost, float]], bool]:
    """Return (top_k_scored, used_fallback)."""
    if not posts:
        return [], False

    candidates = [
        {
            "post_id": p.id,
            "source": p.source.value,
            "title": p.title[:200],
            "body_snippet": p.body[:400],
            "score": p.score,
            "num_comments": p.num_comments,
        }
        for p in posts
    ]
    user = f"Prompt: {prompt}\n\nCandidates:\n{json.dumps(candidates)}"

    try:
        ranked = llm.json_call(_RANKER_SYSTEM, user, _RankedList)
        rel_map = {r.post_id: r.relevance for r in ranked.ranked}
        scored = [(p, rel_map.get(p.id, 0.0)) for p in posts]
        scored.sort(key=lambda t: (t[1], t[0].score, t[0].num_comments), reverse=True)
        return scored[:top_k], False
    except OllamaError:
        scored = [(p, 0.0) for p in posts]
        scored.sort(key=lambda t: (t[0].score + t[0].num_comments), reverse=True)
        return scored[:top_k], True
