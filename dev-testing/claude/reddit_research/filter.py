"""Comment filtering rules per v1.spec §10."""
from __future__ import annotations

import re

from reddit_research.prompts import BOT_AUTHOR_BLOCKLIST, BOT_BODY_PATTERNS, MIN_COMMENT_BODY_CHARS
from reddit_research.schema import RawComment

_BOT_REGEXES = [re.compile(p) for p in BOT_BODY_PATTERNS]


def filter_comments(
    comments: list[RawComment],
    min_score: int = 5,
    max_keep: int = 10,
) -> list[RawComment]:
    kept: list[RawComment] = []
    for c in comments:
        if c.depth != 0:
            continue
        if c.author in BOT_AUTHOR_BLOCKLIST:
            continue
        if c.score < min_score:
            continue
        if len(c.body.strip()) < MIN_COMMENT_BODY_CHARS:
            continue
        if any(rx.search(c.body) for rx in _BOT_REGEXES):
            continue
        kept.append(c)
    kept.sort(key=lambda c: c.score, reverse=True)
    return kept[:max_keep]


def signal_density(
    scraped: int,
    kept: int,
    mean_kept_score: float,
    mean_relevance: float,
) -> float:
    ratio = kept / scraped if scraped else 0.0
    normalized_score = mean_kept_score / 20.0
    raw = ratio * normalized_score * mean_relevance
    return max(0.0, min(1.0, raw))
