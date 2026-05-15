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
from social_scraper.core.schema import (
    PostSummary,
    RawPost,
    RunMeta,
    SourceKind,
    SourceStats,
    TopicConfidence,
)
from social_scraper.core.store.cache import LLMCache
from social_scraper.core.store.reputation import Reputation
from social_scraper.core.store.run import RunWriter
from social_scraper.core.store.timeline import TimelineWriter


class _OllamaEmbedAdapter:
    """Adapts an OllamaClient to the embedder contract used by rank_posts."""

    def __init__(self, llm, model: str) -> None:
        self._llm = llm
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._llm.embed(texts, model=self._model)


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
    # When set, bypass LLM-driven subreddit discovery and use these subs verbatim.
    subreddits: Optional[list[str]] = None
    # Embeddings model used for semantic relevance ranking.
    embed_model: str = "bge-m3:latest"
    # Cosine similarity below this drops posts from summarization.
    # Empirically tuned for bge-m3 — see TODO-tomorrow.md validation notes:
    # genuine on-topic posts score 0.45–0.53, clear noise scores 0.30.
    drop_threshold: float = 0.45
    # Topic-relevance gate: skip summarization when fewer than this many posts
    # cleared the drop threshold.
    min_kept_for_summary: int = 5
    min_keep_ratio: float = 0.10


_TOPIC_CHECK_SYSTEM = (
    "You verify whether a research digest actually answers a user's question. "
    "Reply ONLY with JSON: "
    "{addressed: bool, confidence: 0.0-1.0, rationale: string}. "
    "'addressed' is true only if the summary directly discusses the user's topic. "
    "If the summary is about a different subject, set addressed=false."
)


def _topic_confidence_check(llm, topic: str, narrative: str) -> Optional[TopicConfidence]:
    """Ask the LLM whether the narrative addresses the topic. Best-effort: returns None on error."""
    snippet = narrative[:4000]
    user = f"User topic: {topic}\n\nDigest:\n{snippet}"
    try:
        return llm.json_call(_TOPIC_CHECK_SYSTEM, user, TopicConfidence)
    except OllamaError:
        return None
    except Exception:
        return None


def _prepend_confidence_header(narrative: str, tc: Optional[TopicConfidence]) -> str:
    if tc is None:
        return narrative
    if tc.addressed and tc.confidence >= 0.6:
        header = (
            f"> topic-confidence: {tc.confidence:.2f} — summary addresses query directly\n\n"
        )
    else:
        header = (
            f"> WARN topic-confidence: {tc.confidence:.2f} — "
            f"summary may not address the original query\n\n"
        )
    # Insert after the leading H1 if present, otherwise prepend.
    if narrative.startswith("# "):
        first_nl = narrative.find("\n")
        if first_nl != -1:
            return narrative[: first_nl + 1] + "\n" + header + narrative[first_nl + 1 :].lstrip("\n")
    return header + narrative


def _normalize_sub(name: str) -> str:
    """Strip a leading `r/` or `/r/` prefix without eating other leading 'r's.

    `str.lstrip("r/")` strips any leading char in the set {'r', '/'}, which
    silently mangles names like `rollerskating` -> `ollerskating`.
    """
    s = name.strip()
    if s.startswith("/r/"):
        s = s[3:]
    elif s.startswith("r/"):
        s = s[2:]
    return s


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
            if cfg.subreddits:
                subs = [_normalize_sub(s) for s in cfg.subreddits if s.strip()]
                writer.add_warning(f"discovery_skipped:pinned_subs={','.join(subs)}")
            else:
                subs, _area_slug = discover_subreddits(
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

    # Rank — embeddings cosine sim against the topic (bge-m3 by default).
    embedder = _OllamaEmbedAdapter(llm, cfg.embed_model)
    ranking = rank_posts(
        embedder,
        cfg.topic,
        raw_posts,
        top_k=cfg.top_k,
        drop_threshold=cfg.drop_threshold,
    )
    if ranking.used_fallback:
        writer.add_warning("rank_fallback_used:embedder_failed")

    # Persist full audit trail of ranking decisions (including dropped items).
    writer.write_ranked([
        {
            "post_id": p.id,
            "source": p.source.value,
            "relevance": rel,
            "reason": reason,
            "kept": (p.id in {k.id for k, _, _ in ranking.kept}),
        }
        for p, rel, reason in ranking.ranked
    ])

    # Per-source stats: discovered / ranked / kept / dropped.
    kept_ids_by_source: dict[SourceKind, set[str]] = {}
    for p, _, _ in ranking.kept:
        kept_ids_by_source.setdefault(p.source, set()).add(p.id)
    sources_seen = {p.source for p in raw_posts}
    for source in sources_seen:
        n_disc = sum(1 for p in raw_posts if p.source == source)
        kept_ids = kept_ids_by_source.get(source, set())
        n_kept = len(kept_ids)
        writer.set_source_stats(source, SourceStats(
            discovered=n_disc,
            ranked=n_disc,  # we score every discovered post
            kept=n_kept,
            dropped=n_disc - n_kept,
        ))

    # Topic-relevance gate — skip summarization when too little on-topic content survived.
    n_discovered = len(raw_posts)
    n_kept = len(ranking.kept)
    keep_ratio = (n_kept / n_discovered) if n_discovered else 0.0
    if (
        not ranking.used_fallback
        and n_discovered > 0
        and (n_kept < cfg.min_kept_for_summary or keep_ratio < cfg.min_keep_ratio)
    ):
        writer.mark_topic_mismatch()
        writer.add_warning(
            f"topic_mismatch: only {n_kept} of {n_discovered} posts addressed '{cfg.topic}'"
        )
        writer.write_summary_md(
            f"# {cfg.topic}\n\n"
            f"> topic_mismatch — only {n_kept} of {n_discovered} posts "
            f"cleared the relevance threshold ({cfg.drop_threshold:.2f}). "
            f"Skipping summarization to avoid a confidently-wrong answer.\n\n"
            f"Try a narrower topic phrase, a different `--subreddits` set, or a wider `--window-days`.\n"
        )
        writer.finalize(finished=datetime.now(timezone.utc))
        cache.close()
        return {
            "run_dir": writer.run_dir,
            "summary_path": writer.run_dir / "summary" / "summary.md",
            "warnings": list(writer.meta.warnings),
            "topic_mismatch": True,
        }

    # Fetch deep + summarize per kept item
    summaries: list[PostSummary] = []
    for post, relevance, _reason in ranking.kept:
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

    # Post-summary topic-confidence check — quick LLM second-pass.
    tc = _topic_confidence_check(llm, cfg.topic, narrative)
    if tc is not None:
        writer.set_topic_confidence(tc)
    final_md = _prepend_confidence_header(narrative, tc)
    writer.write_summary_md(final_md)

    # Timeline append
    first_para = final_md.split("\n\n")[1] if "\n\n" in final_md else final_md[:300]
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
        "topic_confidence": tc.model_dump() if tc else None,
    }
