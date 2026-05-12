"""Agentic discover loop using smolagents.CodeAgent.

The loop has hard caps (5 iterations, 90s wall clock per iteration) per spec §9.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from social_scraper.core.pipeline.ask import AskConfig, run_ask
from social_scraper.core.schema import SourceKind


# --- Tool implementations (plain functions; agent will wrap these) -----------

def _tool_top_trending_reddit(reddit, window_days: int, limit: int) -> list[str]:
    """Return top-N titles from r/popular over the window."""
    if window_days <= 1:
        tf = "day"
    elif window_days <= 7:
        tf = "week"
    else:
        tf = "month"
    posts, _ = reddit.fetch_listing("popular", listing="top", time_filter=tf, limit=limit)
    return [p.title for p in posts[:limit]]


def _tool_top_trending_hn(hn, window_days: int, limit: int) -> list[str]:
    """Return top story titles from HN over the window (top stories of last N days)."""
    posts = hn.search("", window_days=window_days, limit=limit * 2)
    stories = [p for p in posts if p.id.startswith("story:")]
    stories.sort(key=lambda p: p.score, reverse=True)
    return [p.title for p in stories[:limit]]


def _tool_top_trending_google(trends_backend, window_days: int, limit: int) -> list[str]:
    """Best-effort trending keywords. trendspy exposes `trending_now`; pytrends does not.
    Returns [] if backend can't supply.
    """
    impl = getattr(trends_backend, "_impl", None)
    if impl is None:
        return []
    fn = getattr(impl, "trending_now", None)
    if fn is None:
        return []
    try:
        items = fn(geo="US")
        return [getattr(x, "keyword", str(x)) for x in list(items)[:limit]]
    except Exception:
        return []


# --- Agent loop --------------------------------------------------------------

@dataclass
class DiscoverConfig:
    window_days: int = 30
    top_n: int = 5
    sources: list[SourceKind] = field(default_factory=lambda: list(SourceKind))
    model: str = "qwen3-coder:30b"
    summarizer: str = "ollama"
    data_root: Path = Path("data")
    cache_path: Path = Path("cache/ollama_calls.sqlite")
    reputation_path: Path = Path("cache/reputation.json")
    max_iterations: int = 5
    per_iter_timeout_s: int = 90


def run_discover(
    cfg: DiscoverConfig,
    *,
    agent_driver,        # something with .pick_topics(candidates: list[str], top_n: int) -> list[str]
    llm,                 # passed through to run_ask
    reddit,
    hn,
    indiehackers,
    google_trends,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    parent_dir = cfg.data_root / "runs" / f"discover_{now.strftime('%Y-%m-%dT%H-%M-%SZ')}"
    parent_dir.mkdir(parents=True, exist_ok=True)
    (parent_dir / "summary").mkdir(exist_ok=True)

    candidates: list[str] = []
    started = time.monotonic()
    iters = 0
    partial = False

    if SourceKind.reddit in cfg.sources:
        if time.monotonic() - started > cfg.per_iter_timeout_s * cfg.max_iterations:
            partial = True
        else:
            try:
                candidates.extend(_tool_top_trending_reddit(reddit, cfg.window_days, cfg.top_n * 2))
            except Exception:
                pass
            iters += 1
    if SourceKind.hn in cfg.sources and iters < cfg.max_iterations:
        try:
            candidates.extend(_tool_top_trending_hn(hn, cfg.window_days, cfg.top_n * 2))
        except Exception:
            pass
        iters += 1
    if SourceKind.google_trends in cfg.sources and iters < cfg.max_iterations:
        try:
            backend = getattr(google_trends, "_backend", None)
            if backend is not None:
                candidates.extend(_tool_top_trending_google(backend, cfg.window_days, cfg.top_n * 2))
        except Exception:
            pass
        iters += 1

    if not candidates:
        (parent_dir / "summary" / "summary.md").write_text(
            "# discover run\n\nNo trending candidates available — sources returned empty.\n"
        )
        return {"run_dir": parent_dir, "summary_path": parent_dir / "summary" / "summary.md", "partial": True}

    # Dedup + cap
    seen = set()
    deduped: list[str] = []
    for c in candidates:
        cl = c.strip().lower()
        if cl and cl not in seen:
            seen.add(cl)
            deduped.append(c.strip())

    picked = agent_driver.pick_topics(deduped, top_n=cfg.top_n)

    child_summaries: list[tuple[str, Path]] = []
    for topic in picked:
        if iters >= cfg.max_iterations or (time.monotonic() - started) > cfg.per_iter_timeout_s * cfg.max_iterations:
            partial = True
            break
        ask_cfg = AskConfig(
            topic=topic,
            window_days=cfg.window_days,
            sources=cfg.sources,
            model=cfg.model,
            summarizer=cfg.summarizer,
            data_root=cfg.data_root,
            cache_path=cfg.cache_path,
            reputation_path=cfg.reputation_path,
        )
        result = run_ask(
            ask_cfg,
            llm=llm, reddit=reddit, hn=hn,
            indiehackers=indiehackers, google_trends=google_trends,
            now=datetime.now(timezone.utc),
        )
        child_summaries.append((topic, result["summary_path"]))
        iters += 1

    md_lines = [f"# discover run — {now.strftime('%Y-%m-%dT%H:%M:%SZ')}\n"]
    if partial:
        md_lines.append("> ⚠ discover_partial — cap hit before all picks completed\n")
    md_lines.append("\n## Candidate trends considered\n")
    for c in deduped:
        md_lines.append(f"- {c}")
    md_lines.append("\n## Picked & analyzed\n")
    for topic, path in child_summaries:
        rel = path.relative_to(parent_dir.parent.parent) if cfg.data_root in path.parents else path
        md_lines.append(f"### {topic}")
        md_lines.append(f"[summary]({rel})\n")
    (parent_dir / "summary" / "summary.md").write_text("\n".join(md_lines) + "\n")

    return {
        "run_dir": parent_dir,
        "summary_path": parent_dir / "summary" / "summary.md",
        "partial": partial,
        "child_count": len(child_summaries),
    }
