"""Typer CLI + the `run_ask` orchestrator that the test drives directly."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import httpx
import typer

from reddit_research.cache import Cache, hash_prompt
from reddit_research.discover import discover
from reddit_research.fetch import RedditClient, make_client
from reddit_research.filter import filter_comments, signal_density
from reddit_research.llm import LLM, LLMError
from reddit_research.rank import rank_posts
from reddit_research.render import append_jsonl, slugify, write_json, write_markdown
from reddit_research.reputation import Reputation
from reddit_research.schema import (
    Digest,
    NotablePost,
    PostSummary,
    PromptRow,
    RawComment,
    RawPost,
    SentimentJsonlRow,
    SubSentiment,
)
from reddit_research.summarize import (
    collect_themes,
    digest_narrative,
    pick_notable,
    sub_sentiment,
    summarize_post,
)

CLAUDE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = CLAUDE_ROOT / "data"
DEFAULT_CACHE_DB = CLAUDE_ROOT / "cache" / "cache.db"
DEFAULT_REPUTATION = CLAUDE_ROOT / "cache" / "reputation.json"


def _now_utc_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_ask(
    prompt: str,
    *,
    listing: str = "top",
    time_filter: str = "month",
    limit: int = 25,
    top_k: int = 15,
    comments_per_post: int = 10,
    min_comment_score: int = 5,
    max_subs: int = 8,
    model: str = "qwen3-coder:30b",
    out_dir: Path | None = None,
    cache_db: Path | None = None,
    reputation_path: Path | None = None,
    ticker: str | None = None,
    emit_sentiment_dir: Path | None = None,
    use_cache: bool = True,
    offline: bool = False,
    llm: LLM | None = None,
    reddit: RedditClient | None = None,
    stream_digest: bool = True,
    out_stream: Any = None,
) -> dict:
    """Run the full ask pipeline. DI for tests.

    Returns: {"digest": Digest, "md_path": Path, "json_path": Path,
              "jsonl_path": Path | None, "posts": dict, "summaries": dict}.
    """
    out_dir = (out_dir or DEFAULT_DATA_DIR)
    cache_db = (cache_db or DEFAULT_CACHE_DB)
    reputation_path = (reputation_path or DEFAULT_REPUTATION)
    stream = out_stream if out_stream is not None else sys.stdout

    out_dir.mkdir(parents=True, exist_ok=True)
    cache_db.parent.mkdir(parents=True, exist_ok=True)

    if llm is None:
        llm = LLM(model=model)
        if not offline and not llm.ping():
            raise SystemExit(
                "Ollama not reachable at http://localhost:11434 — start it with `ollama serve`."
            )

    owns_http = False
    if reddit is None:
        client = make_client()
        owns_http = True
        reddit = RedditClient(client, user_agent=client.headers.get("User-Agent", ""))

    cache = Cache(cache_db)
    rep = Reputation(reputation_path)
    rep.load()

    try:
        prompt_hash = hash_prompt(prompt, listing, time_filter)
        if use_cache:
            cached = cache.get_prompt(prompt_hash)
            if cached is not None:
                digest = Digest.model_validate_json(cached.digest_json)
                _emit_cached(digest, stream)
                return {
                    "digest": digest,
                    "md_path": Path(cached.digest_md_path) if cached.digest_md_path else None,
                    "json_path": None,
                    "jsonl_path": None,
                    "posts": {},
                    "summaries": {},
                    "from_cache": True,
                }

        final_subs, area_slug = discover(llm, reddit, prompt, rep.load(), max_subs=max_subs)
        if not final_subs:
            raise SystemExit("No usable subreddits found — try a more specific prompt.")

        candidate_posts: dict[str, RawPost] = {}
        for sub in final_subs:
            posts, _ = reddit.fetch_listing(
                sub, listing=listing, time_filter=time_filter, limit=limit
            )
            for p in posts:
                candidate_posts[p.id] = p

        if not candidate_posts:
            raise SystemExit("No posts returned for any subreddit.")

        ranked = rank_posts(llm, prompt, list(candidate_posts.values()), top_k=top_k)
        top_posts: list[tuple[RawPost, float]] = ranked[:top_k]

        posts_by_id: dict[str, RawPost] = {}
        summaries_by_id: dict[str, PostSummary] = {}
        kept_counts_by_sub: dict[str, dict[str, int]] = {}

        for post, relevance in top_posts:
            cached_post = cache.get_post(post.id) if use_cache else None
            if cached_post is not None and cached_post.top_comments:
                full_post = cached_post
            else:
                full_post = reddit.fetch_comments(post.subreddit, post.id, limit=comments_per_post)
                cache.put_post(full_post)
            posts_by_id[post.id] = full_post

            scraped = len(full_post.top_comments)
            kept = filter_comments(
                full_post.top_comments,
                min_score=min_comment_score,
                max_keep=comments_per_post,
            )
            sub_stats = kept_counts_by_sub.setdefault(
                full_post.subreddit, {"scraped": 0, "kept": 0, "kept_score_sum": 0}
            )
            sub_stats["scraped"] += scraped
            sub_stats["kept"] += len(kept)
            sub_stats["kept_score_sum"] += sum(c.score for c in kept)

            existing = (
                cache.get_summary(post.id, model) if use_cache else None
            )
            if existing is not None:
                summary = existing
                summary.relevance_to_prompt = relevance
            else:
                try:
                    summary = summarize_post(
                        llm, prompt, full_post, kept, relevance=relevance
                    )
                except LLMError:
                    summary = None
                if summary is None:
                    continue
                cache.put_summary(post.id, model, summary)
            summaries_by_id[post.id] = summary

        if not summaries_by_id:
            raise SystemExit("All summarizations failed — aborting.")

        subs_actually_used = sorted({posts_by_id[pid].subreddit for pid in summaries_by_id})

        sentiments: list[SubSentiment] = []
        for sub in subs_actually_used:
            sub_summaries = [
                s for pid, s in summaries_by_id.items() if posts_by_id[pid].subreddit == sub
            ]
            n_comments_sub = kept_counts_by_sub.get(sub, {}).get("kept", 0)
            sentiments.append(
                sub_sentiment(llm, prompt, sub, sub_summaries, n_comments_sub)
            )

        themes = collect_themes(list(summaries_by_id.values()))
        notable = pick_notable(list(summaries_by_id.values()), posts_by_id)

        narrative_parts: list[str] = []
        if stream_digest:
            stream.write("\n# Digest\n\n")
            stream.flush()
            for chunk in digest_narrative(
                llm, prompt, list(summaries_by_id.values()), sentiments, stream=True
            ):
                stream.write(chunk)
                stream.flush()
                narrative_parts.append(chunk)
            stream.write("\n")
            narrative = "".join(narrative_parts)
        else:
            result = digest_narrative(
                llm, prompt, list(summaries_by_id.values()), sentiments, stream=False
            )
            narrative = result if isinstance(result, str) else "".join(result)

        digest = Digest(
            prompt=prompt,
            generated_utc=_now_utc_z(),
            subreddits_used=subs_actually_used,
            post_count=len(summaries_by_id),
            themes=themes,
            narrative=narrative,
            notable_posts=notable,
            per_sub_sentiment=sentiments,
        )

        slug = slugify(prompt)
        ts = digest.generated_utc.replace(":", "-")
        md_path = out_dir / f"{slug}_{ts}.md"
        json_path = out_dir / f"{slug}_{ts}.json"
        write_markdown(md_path, digest, posts_by_id, summaries_by_id)
        write_json(json_path, digest, posts_by_id, summaries_by_id)

        jsonl_path: Path | None = None
        if ticker and emit_sentiment_dir:
            jsonl_path = emit_sentiment_dir / f"{ticker.upper()}.jsonl"
            rows: list[SentimentJsonlRow] = [
                SentimentJsonlRow(
                    ts=digest.generated_utc,
                    ticker=ticker.upper(),
                    sub=s.subreddit,
                    score=s.score,
                    confidence=s.confidence,
                    n_posts=s.n_posts,
                    n_comments=s.n_comments,
                    theme=s.theme,
                    prompt=prompt,
                    model=model,
                )
                for s in sentiments
            ]
            append_jsonl(jsonl_path, rows)

        sub_signals: dict[str, dict] = {}
        for sub, stats in kept_counts_by_sub.items():
            kept_n = stats["kept"]
            scraped_n = stats["scraped"]
            mean_kept_score = (stats["kept_score_sum"] / kept_n) if kept_n else 0.0
            mean_rel = (
                sum(
                    s.relevance_to_prompt
                    for pid, s in summaries_by_id.items()
                    if posts_by_id[pid].subreddit == sub
                )
                / max(1, sum(1 for pid in summaries_by_id if posts_by_id[pid].subreddit == sub))
            )
            sub_signals[sub] = {
                "signal_density": signal_density(scraped_n, kept_n, mean_kept_score, mean_rel),
                "n_posts": sum(
                    1 for pid in summaries_by_id if posts_by_id[pid].subreddit == sub
                ),
            }
        rep.auto_update(area_slug, sub_signals)
        rep.save()

        cache.put_prompt(
            PromptRow(
                prompt_hash=prompt_hash,
                prompt_text=prompt,
                ran_at=digest.generated_utc,
                subreddits=subs_actually_used,
                post_ids=list(summaries_by_id.keys()),
                digest_md_path=str(md_path),
                digest_json=digest.model_dump_json(),
            )
        )

        return {
            "digest": digest,
            "md_path": md_path,
            "json_path": json_path,
            "jsonl_path": jsonl_path,
            "posts": posts_by_id,
            "summaries": summaries_by_id,
            "from_cache": False,
        }
    finally:
        cache.close()
        if owns_http and reddit is not None:
            try:
                reddit.client.close()  # type: ignore[attr-defined]
            except Exception:
                pass


def _emit_cached(digest: Digest, stream: Any) -> None:
    stream.write(f"\n# Digest (from cache, ran at {digest.generated_utc})\n\n")
    stream.write(digest.narrative)
    stream.write("\n")
    stream.flush()


app = typer.Typer(help="Prompt-driven Reddit research with local LLM summarization.")


@app.command()
def ask(
    prompt: str = typer.Argument(...),
    listing: str = typer.Option("top"),
    time_filter: str = typer.Option("month", "--time-filter"),
    limit: int = typer.Option(25),
    top: int = typer.Option(15),
    comments: int = typer.Option(10),
    min_comment_score: int = typer.Option(5, "--min-comment-score"),
    max_subs: int = typer.Option(8, "--max-subs"),
    model: str = typer.Option("qwen3-coder:30b"),
    out: Path = typer.Option(DEFAULT_DATA_DIR, "--out"),
    ticker: str | None = typer.Option(None, "--ticker"),
    emit_sentiment: Path | None = typer.Option(None, "--emit-sentiment"),
    no_cache: bool = typer.Option(False, "--no-cache"),
    offline: bool = typer.Option(False, "--offline"),
) -> None:
    if ticker and not emit_sentiment:
        raise typer.BadParameter("--ticker requires --emit-sentiment")
    run_ask(
        prompt,
        listing=listing,
        time_filter=time_filter,
        limit=limit,
        top_k=top,
        comments_per_post=comments,
        min_comment_score=min_comment_score,
        max_subs=max_subs,
        model=model,
        out_dir=out,
        ticker=ticker,
        emit_sentiment_dir=emit_sentiment,
        use_cache=not no_cache,
        offline=offline,
    )


@app.command()
def promote(sub: str, area: str) -> None:
    rep = Reputation(DEFAULT_REPUTATION)
    rep.load()
    rep.promote(area, sub)
    rep.save()
    typer.echo(f"Promoted r/{sub} for area '{area}'.")


@app.command()
def demote(sub: str, area: str) -> None:
    rep = Reputation(DEFAULT_REPUTATION)
    rep.load()
    rep.demote(area, sub)
    rep.save()
    typer.echo(f"Demoted r/{sub} for area '{area}'.")


@app.command()
def recall(
    latest: bool = typer.Option(True, "--latest/--no-latest"),
    prompt_hash: str | None = typer.Option(None, "--prompt-hash"),
) -> None:
    cache = Cache(DEFAULT_CACHE_DB)
    try:
        if prompt_hash:
            row = cache.get_prompt(prompt_hash)
        elif latest:
            rows = cache.list_prompts(limit=1)
            row = rows[0] if rows else None
        else:
            row = None
        if row is None:
            typer.echo("No matching prompt found.")
            raise typer.Exit(1)
        digest = Digest.model_validate_json(row.digest_json)
        _emit_cached(digest, sys.stdout)
    finally:
        cache.close()


@app.command("list-prompts")
def list_prompts(limit: int = typer.Option(20)) -> None:
    cache = Cache(DEFAULT_CACHE_DB)
    try:
        for row in cache.list_prompts(limit=limit):
            typer.echo(f"{row.ran_at}  {row.prompt_hash[:12]}  {row.prompt_text}")
    finally:
        cache.close()


@app.command()
def purge() -> None:
    cache = Cache(DEFAULT_CACHE_DB)
    try:
        counts = cache.purge(days=30)
        typer.echo(f"Purged: {counts}")
    finally:
        cache.close()


@app.command()
def stats() -> None:
    cache = Cache(DEFAULT_CACHE_DB)
    try:
        typer.echo(json.dumps(cache.stats(), indent=2))
    finally:
        cache.close()


if __name__ == "__main__":
    app()
