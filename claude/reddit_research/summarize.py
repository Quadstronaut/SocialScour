"""Per-post summary, per-sub sentiment, and digest narrative — §11."""
from __future__ import annotations

import math
from collections import Counter
from typing import TYPE_CHECKING, Iterator

from pydantic import BaseModel

from reddit_research.llm import LLMError
from reddit_research.prompts import DIGEST_SYSTEM, POST_SUMMARY_SYSTEM, SUB_SENTIMENT_SYSTEM
from reddit_research.schema import NotablePost, PostSummary, RawComment, RawPost, SubSentiment

if TYPE_CHECKING:
    from reddit_research.llm import LLM


class _PartialSummary(BaseModel):
    one_sentence: str
    three_bullets: list[str]
    key_quotes: list[str] = []
    sentiment: str
    topics: list[str]


class _PartialSent(BaseModel):
    score: float
    confidence: float
    theme: str


def _build_post_user_msg(
    prompt: str,
    post: RawPost,
    kept_comments: list[RawComment],
) -> str:
    parts: list[str] = [
        f"Prompt: {prompt}",
        f"Title: {post.title}",
        f"Body: {post.selftext[:2000]}",
        "Comments:",
    ]
    for c in kept_comments:
        body = c.body[:600]
        parts.append(f"[score {c.score}] {body}")
    return "\n".join(parts)


def summarize_post(
    llm: LLM,
    prompt: str,
    post: RawPost,
    kept_comments: list[RawComment],
    *,
    relevance: float = 0.0,
) -> PostSummary | None:
    user = _build_post_user_msg(prompt, post, kept_comments)
    try:
        partial: _PartialSummary = llm.json_call(POST_SUMMARY_SYSTEM, user, _PartialSummary)
    except LLMError:
        return None

    bullets = (partial.three_bullets + ["", "", ""])[:3]
    topics = partial.topics[:5] if partial.topics else ["general"]

    return PostSummary(
        post_id=post.id,
        one_sentence=partial.one_sentence,
        three_bullets=bullets,
        key_quotes=partial.key_quotes[:3],
        sentiment=partial.sentiment,  # type: ignore[arg-type]
        topics=topics,
        relevance_to_prompt=relevance,
    )


def sub_sentiment(
    llm: LLM,
    prompt: str,
    sub: str,
    summaries: list[PostSummary],
    n_comments_total: int,
) -> SubSentiment:
    bullets = "\n".join(f"- {s.one_sentence}" for s in summaries)
    user = f"Prompt: {prompt}\n\nPosts from r/{sub}:\n{bullets}"

    partial: _PartialSent = llm.json_call(SUB_SENTIMENT_SYSTEM, user, _PartialSent)

    return SubSentiment(
        subreddit=sub,
        score=max(-1.0, min(1.0, partial.score)),
        confidence=max(0.0, min(1.0, partial.confidence)),
        n_posts=len(summaries),
        n_comments=n_comments_total,
        theme=partial.theme,
    )


def digest_narrative(
    llm: LLM,
    prompt: str,
    summaries: list[PostSummary],
    sentiments: list[SubSentiment],
    stream: bool = False,
    posts_by_id: dict[str, RawPost] | None = None,
) -> str | Iterator[str]:
    def _sub(s: PostSummary) -> str:
        if posts_by_id:
            post = posts_by_id.get(s.post_id)
            if post:
                return post.subreddit
        return "unknown"

    post_lines = "\n".join(f"[r/{_sub(s)}] {s.one_sentence}" for s in summaries)
    sent_lines = "\n".join(
        f"r/{s.subreddit}: score={s.score:.2f}, confidence={s.confidence:.2f} — {s.theme}"
        for s in sentiments
    )
    user = (
        f"Prompt: {prompt}\n\n"
        f"Post summaries:\n{post_lines}\n\n"
        f"Per-subreddit sentiment:\n{sent_lines}"
    )
    return llm.text_call(DIGEST_SYSTEM, user, stream=stream)


def collect_themes(summaries: list[PostSummary], top_n: int = 8) -> list[str]:
    counter: Counter[str] = Counter()
    for s in summaries:
        counter.update(s.topics)
    return [tag for tag, _ in counter.most_common(top_n)]


def pick_notable(
    summaries: list[PostSummary],
    posts_by_id: dict[str, RawPost],
    top_n: int = 5,
) -> list[NotablePost]:
    def _key(s: PostSummary) -> float:
        post = posts_by_id.get(s.post_id)
        if post is None:
            return 0.0
        return s.relevance_to_prompt * math.log1p(post.score)

    ranked = sorted(summaries, key=_key, reverse=True)[:top_n]
    result: list[NotablePost] = []
    for s in ranked:
        post = posts_by_id.get(s.post_id)
        if post is None:
            continue
        why = f"r/{post.subreddit}, score {post.score}, relevance {s.relevance_to_prompt:.2f}"
        result.append(NotablePost(post_id=s.post_id, why_notable=why))
    return result
