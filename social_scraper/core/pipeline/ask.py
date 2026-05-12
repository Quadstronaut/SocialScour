"""Deterministic ask pipeline orchestrator (spec §8)."""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from social_scraper.core.llm.ollama import OllamaError
from social_scraper.core.pipeline.discover_subs import discover_subreddits
from social_scraper.core.pipeline.narrate import narrate
from social_scraper.core.pipeline.rank import rank_posts
from social_scraper.core.pipeline.summarize import summarize_post
from social_scraper.core.schema import PostSummary, RawPost, RunMeta, SourceKind
from social_scraper.core.store.cache import LLMCache
from social_scraper.core.store.reputation import Reputation
from social_scraper.core.store.run import RunWriter
from social_scraper.core.store.timeline import TimelineWriter


@dataclass
class AskConfig:
    topic: str
    window_days: int = 30
    sources: list[SourceKind] = field(default_factory=lambda: list(SourceKind))
    model: str = "qwen3-coder:30b"
    summarizer: str = "ollama"  # "ollama" | "claude"
    data_root: Path = Path("data")
    cache_path: Path = Path("cache/ollama_calls.sqlite")
    reputation_path: Path = Path("cache/reputation.json")
    listing: str = "top"
    time_filter: str = "month"
    limit: int = 25
    top_k: int = 15
    comments_per_post: int = 10
    min_comment_score: int = 5
    max_subs: int = 8


def _window_to_time_filter(window_days: int) -> str:
    if window_days <= 1:
        return "day"
    if window_days <= 7:
        return "week"
    if window_days <= 30:
        return "month"
    if window_days <= 365:
        return "year"
    return "all"


def run_ask(
    cfg: AskConfig,
    *,
    llm,
    reddit,
    hn,
    indiehackers,
    google_trends,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    writer = RunWriter(
        root=cfg.data_root,
        topic=cfg.topic,
        sources=cfg.sources,
        window_days=cfg.window_days,
        model=cfg.model,
        summarizer=cfg.summarizer,
        started=now,
    )
    cache = LLMCache(cfg.cache_path)
    rep = Reputation(cfg.reputation_path)
    rep_data = rep.load()

    raw_posts: list[RawPost] = []

    # --- Reddit branch
    if SourceKind.reddit in cfg.sources:
        try:
            subs, area_slug = discover_subreddits(
                llm, reddit, cfg.topic, rep_data, max_subs=cfg.max_subs,
            )
            tf = _window_to_time_filter(cfg.window_days)
            for sub in subs:
                try:
                    posts, _ = reddit.fetch_listing(
                        sub, listing=cfg.listing, time_filter=tf, limit=cfg.limit,
                    )
                    raw_posts.extend(posts)
                except Exception as exc:
                    writer.add_warning(f"reddit_listing_failed:{sub}:{exc}")
        except Exception as exc:
            writer.add_warning(f"reddit_branch_failed:{exc}")
            writer.mark_blocked(SourceKind.reddit)

    # --- HN branch
    if SourceKind.hn in cfg.sources:
        try:
            hn_posts = hn.search(cfg.topic, window_days=cfg.window_days, limit=50)
            raw_posts.extend(hn_posts)
        except Exception as exc:
            writer.add_warning(f"hn_failed:{exc}")
            writer.mark_blocked(SourceKind.hn)

    # --- IndieHackers branch (best-effort: fetch one category)
    if SourceKind.indiehackers in cfg.sources:
        try:
            ih_posts = indiehackers.fetch_listing("ideas-and-validation", limit=20)
            raw_posts.extend(ih_posts)
        except Exception as exc:
            writer.add_warning(f"ih_failed:{exc}")
            writer.mark_blocked(SourceKind.indiehackers)

    # --- Trends branch (stored as a blob, not a "post")
    if SourceKind.google_trends in cfg.sources:
        try:
            trends = google_trends.snapshot(cfg.topic, window_days=cfg.window_days)
            writer.write_raw_blob(SourceKind.google_trends, {
                "keyword": trends.keyword,
                "window_days": trends.window_days,
                "interest_over_time": trends.interest_over_time,
                "top_related": trends.top_related,
            })
        except Exception as exc:
            writer.add_warning(f"trends_failed:{exc}")
            writer.mark_blocked(SourceKind.google_trends)

    if not raw_posts and SourceKind.google_trends not in writer.meta.sources:
        writer.add_warning("no_data_collected")
        writer.write_summary_md(
            f"# {cfg.topic}\n\nNo data collected — try a wider window or different sources.\n"
        )
        writer.finalize(finished=datetime.now(timezone.utc))
        cache.close()
        return {"run_dir": writer.run_dir, "summary_path": writer.run_dir / "summary" / "summary.md"}

    # Group + write raw
    for source in {p.source for p in raw_posts}:
        writer.write_raw(source, [p for p in raw_posts if p.source == source])

    # Rank
    ranked, used_rank_fallback = rank_posts(llm, cfg.topic, raw_posts, top_k=cfg.top_k)
    if used_rank_fallback:
        writer.add_warning("rank_fallback_used")
    writer.write_ranked([
        {"post_id": p.id, "source": p.source.value, "relevance": rel}
        for p, rel in ranked
    ])

    # Fetch deep + summarize per top item
    summaries: list[PostSummary] = []
    for post, relevance in ranked:
        full_post = post
        if post.source == SourceKind.reddit and post.subreddit:
            try:
                full_post = reddit.fetch_comments(
                    post.subreddit, post.id, limit=cfg.comments_per_post,
                )
            except Exception as exc:
                writer.add_warning(f"reddit_comments_failed:{post.id}:{exc}")

        cache_key = LLMCache.make_key(
            f"item_id={full_post.id}",
            f"model={cfg.model}",
            f"role=summarize",
        )
        cached = cache.get(cache_key)
        if cached is not None:
            try:
                summary = PostSummary.model_validate_json(cached)
                summary.relevance_to_prompt = relevance
                summaries.append(summary)
                continue
            except Exception:
                pass

        summary, fallback = summarize_post(llm, cfg.topic, full_post, relevance=relevance)
        if fallback:
            writer.add_warning(f"summarize_fallback:{full_post.id}")
        summaries.append(summary)
        cache.put(cache_key, summary.model_dump_json())

    # Narrate (streamed to stdout AND captured for the file)
    buf = io.StringIO()
    narrative = narrate(llm, cfg.topic, summaries, out_stream=buf)
    writer.write_summary_md(narrative)

    # Timeline append
    first_para = narrative.split("\n\n")[1] if "\n\n" in narrative else narrative[:300]
    TimelineWriter(cfg.data_root, writer.slug).append(
        when=now, run_dir=writer.run_dir, verdict=first_para,
    )

    finished = datetime.now(timezone.utc)
    writer.finalize(finished=finished)
    cache.close()

    return {
        "run_dir": writer.run_dir,
        "summary_path": writer.run_dir / "summary" / "summary.md",
        "narrative_preview": first_para,
        "warnings": list(writer.meta.warnings),
    }
