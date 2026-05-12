"""Per-item summarization step."""
from __future__ import annotations

from social_scraper.core.llm.ollama import OllamaError
from social_scraper.core.schema import PostSummary, RawPost


_SUMMARIZE_SYSTEM = (
    "You summarize a single social-media post (+ top comments) in 3-5 sentences. "
    "Stay factual. Pull out themes (3-5 short tags). Score relevance 0.0–1.0 to the "
    "user's research prompt."
)


def summarize_post(
    llm,
    prompt: str,
    post: RawPost,
    relevance: float,
) -> tuple[PostSummary, bool]:
    """Return (PostSummary, used_fallback)."""
    comments_text = "\n".join(f"- ({c.score}) {c.body}" for c in post.top_comments[:5])
    user = (
        f"Research prompt: {prompt}\n\n"
        f"Source: {post.source.value}\n"
        f"Title: {post.title}\n\n"
        f"Body:\n{post.body[:2000]}\n\n"
        f"Top comments:\n{comments_text}"
    )
    try:
        result = llm.json_call(_SUMMARIZE_SYSTEM, user, PostSummary)
        # Ensure post_id/source match (LLM may have echoed them differently).
        result.post_id = post.id
        result.source = post.source
        return result, False
    except OllamaError:
        body_extract = (post.body or post.title)[:800]
        if post.top_comments:
            body_extract += f"\n\nTop comment: {post.top_comments[0].body[:300]}"
        return (
            PostSummary(
                post_id=post.id,
                source=post.source,
                summary=body_extract,
                themes=[],
                relevance_to_prompt=relevance,
            ),
            True,
        )
