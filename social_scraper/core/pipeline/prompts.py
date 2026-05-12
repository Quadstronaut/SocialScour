"""LLM prompt constants for the discovery pipeline."""

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
