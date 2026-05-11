"""Pass-1 LLM relevance ranker per v1.spec §9."""
from __future__ import annotations

import json

from pydantic import BaseModel

from reddit_research.llm import LLM
from reddit_research.prompts import RANKER_SYSTEM
from reddit_research.schema import RawPost


class _RankResult(BaseModel):
    post_id: str
    relevance: float


class _RankedList(BaseModel):
    ranked: list[_RankResult]


def rank_posts(
    llm: LLM,
    prompt: str,
    posts: list[RawPost],
    top_k: int = 15,
) -> list[tuple[RawPost, float]]:
    candidates = [
        {
            "post_id": p.id,
            "sub": p.subreddit,
            "title": p.title,
            "selftext_snippet": p.selftext[:400],
            "score": p.score,
            "num_comments": p.num_comments,
        }
        for p in posts
    ]
    user = f"Prompt: {prompt}\n\nCandidates:\n{json.dumps(candidates)}"
    ranked_list = llm.json_call(RANKER_SYSTEM, user, _RankedList)

    relevance_map: dict[str, float] = {r.post_id: r.relevance for r in ranked_list.ranked}

    scored = [
        (p, relevance_map.get(p.id, 0.0))
        for p in posts
    ]
    scored.sort(key=lambda t: (t[1], t[0].score), reverse=True)
    return scored[:top_k]
