"""All LLM prompt constants and tunables in one place."""

POST_SUMMARY_SYSTEM = (
    "You summarize Reddit posts for downstream LLMs and humans. Be faithful, "
    "concrete, and quote real comments verbatim. Never invent facts. Output ONLY "
    "valid JSON matching this schema: "
    '{"one_sentence": str (<=25 words), '
    '"three_bullets": [str, str, str] (exactly 3), '
    '"key_quotes": [str, ...] (0-3 verbatim comment quotes), '
    '"sentiment": "positive"|"neutral"|"negative"|"mixed", '
    '"topics": [str, ...] (1-5 lowercase tags)}.'
)

DIGEST_SYSTEM = (
    "You write a 4-8 sentence plain-English briefing on what Reddit communities "
    "are saying about the user's question. Name specific themes, tensions, and "
    "notable threads. No hedging. No bullet points; flowing prose."
)

DISCOVER_SYSTEM = (
    "You propose Reddit subreddit names (without the r/ prefix) likely to host "
    "substantive discussion of the user's prompt. Only propose subreddits you "
    "are reasonably confident actually exist. Bogus or hallucinated names will "
    "be rejected by verification. Return ONLY valid JSON: "
    '{"subreddits": [str, ...] (5-15 names)}.'
)

TOPIC_AREA_SYSTEM = (
    "Classify the user's prompt into a topic area for a reputation database. "
    "If one of the existing areas fits well, return its slug. Otherwise propose a "
    "new short snake_case slug. Return ONLY valid JSON: "
    '{"area": str, "new": bool}.'
)

RANKER_SYSTEM = (
    "Rank Reddit posts by how directly they help answer the user's question. "
    "Score 0..1 (1=directly answers it, 0=irrelevant). Strongly penalize meme, "
    "joke, or circlejerk content. Return ONLY valid JSON: "
    '{"ranked": [{"post_id": str, "relevance": float}, ...]}.'
)

SUB_SENTIMENT_SYSTEM = (
    "Score the overall sentiment of these Reddit posts regarding the user's "
    "prompt. Return ONLY valid JSON: "
    '{"score": float (-1..1), "confidence": float (0..1), "theme": str (one short sentence)}.'
)

# --- Filtering ---

BOT_AUTHOR_BLOCKLIST = {
    "AutoModerator",
    "[deleted]",
    "[removed]",
}

BOT_BODY_PATTERNS = [
    r"^I am a bot",
    r"^\*?\*?Bot",
    r"This action was performed automatically",
]

MIN_COMMENT_BODY_CHARS = 120  # "not very very short" per user requirement
