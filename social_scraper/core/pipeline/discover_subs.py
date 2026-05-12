"""Subreddit discovery pipeline per v1.spec §7."""
from __future__ import annotations

from pydantic import BaseModel

from social_scraper.core.sources.reddit import RedditClient
from social_scraper.core.pipeline.prompts import DISCOVER_SYSTEM, TOPIC_AREA_SYSTEM


class _Proposal(BaseModel):
    subreddits: list[str]


class _TopicArea(BaseModel):
    area: str
    new: bool


def propose_subreddits(llm, prompt: str) -> list[str]:
    result = llm.json_call(DISCOVER_SYSTEM, prompt, _Proposal)
    return [s.strip().lstrip("r/") for s in result.subreddits]


def verify_subreddits(reddit: RedditClient, names: list[str]) -> list[dict]:
    kept: list[dict] = []
    for name in names:
        data = reddit.about_subreddit(name)
        if data is None:
            continue
        if data.get("subreddit_type") != "public":
            continue
        if (data.get("subscribers") or 0) <= 1000:
            continue
        kept.append(
            {
                "name": data.get("display_name", name),
                "subscribers": data.get("subscribers", 0),
                "subreddit_type": data.get("subreddit_type"),
                "over18": bool(data.get("over18", False)),
            }
        )
    return kept


def merge_search(reddit: RedditClient, prompt: str, current: list[dict]) -> list[dict]:
    existing_names = {d["name"].lower() for d in current}
    results = reddit.search_subreddits(prompt, limit=10)
    merged = list(current)
    for r in results:
        subs = r.get("subscribers") or 0
        name = r.get("display_name", "")
        if subs <= 1000:
            continue
        if name.lower() in existing_names:
            continue
        merged.append(
            {
                "name": name,
                "subscribers": subs,
                "subreddit_type": r.get("subreddit_type"),
                "over18": bool(r.get("over18", False)),
            }
        )
        existing_names.add(name.lower())
    return merged


def classify_topic_area(llm, prompt: str, existing_areas: list[str]) -> tuple[str, bool]:
    user = f"Existing areas: {existing_areas}\n\nPrompt: {prompt}"
    result = llm.json_call(TOPIC_AREA_SYSTEM, user, _TopicArea)
    return result.area, result.new


def discover_subreddits(
    llm,
    reddit: RedditClient,
    prompt: str,
    reputation: dict,
    max_subs: int = 8,
) -> tuple[list[str], str]:
    topic_areas = reputation.get("topic_areas", {})
    existing_areas = list(topic_areas.keys())
    area_slug, _is_new = classify_topic_area(llm, prompt, existing_areas)

    proposed_names = propose_subreddits(llm, prompt)
    verified = verify_subreddits(reddit, proposed_names)
    merged = merge_search(reddit, prompt, verified)

    reputed_subs = topic_areas.get(area_slug, {}).get("subs", {})

    always_include: list[str] = [
        name for name, meta in reputed_subs.items() if meta.get("promoted", False)
    ]
    top3_reputed: list[str] = sorted(
        (name for name, meta in reputed_subs.items() if not meta.get("promoted", False)),
        key=lambda n: reputed_subs[n].get("score", 0),
        reverse=True,
    )[:3]

    seen: set[str] = set()
    final: list[str] = []

    for name in always_include:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            final.append(name)

    for name in top3_reputed:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            final.append(name)

    for entry in merged:
        name = entry["name"]
        key = name.lower()
        if key not in seen:
            seen.add(key)
            final.append(name)

    return final[:max_subs], area_slug
