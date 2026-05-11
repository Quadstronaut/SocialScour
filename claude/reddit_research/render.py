"""Markdown / JSON / JSONL output writers per v1.spec §16."""
from __future__ import annotations

import json
import re
from pathlib import Path

from reddit_research.schema import Digest, PostSummary, RawPost, SentimentJsonlRow


def slugify(text: str, max_len: int = 60) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")
    return text[:max_len]


def write_markdown(
    path: Path,
    digest: Digest,
    posts_by_id: dict[str, RawPost],
    summaries_by_id: dict[str, PostSummary],
) -> None:
    lines: list[str] = []

    lines.append(f"# {digest.prompt} — {digest.generated_utc}")
    lines.append("")
    lines.append(digest.narrative)
    lines.append("")
    lines.append(f"**Themes:** {', '.join(digest.themes)}")
    lines.append(f"**Subreddits used:** {', '.join(digest.subreddits_used)}")
    lines.append("")

    lines.append("## Notable posts")
    for notable in digest.notable_posts:
        post = posts_by_id.get(notable.post_id)
        summary = summaries_by_id.get(notable.post_id)
        if post is None or summary is None:
            continue
        lines.append(
            f"- **{post.title}** (r/{post.subreddit}, score {post.score},"
            f" {post.num_comments} comments) — {notable.why_notable}"
        )
        lines.append(f"  {summary.one_sentence}")
        for bullet in summary.three_bullets:
            lines.append(f"  - {bullet}")
        for quote in summary.key_quotes:
            lines.append(f"  > {quote}")
        lines.append(f"  [link]({post.permalink})")
        lines.append("")

    lines.append("## Per-subreddit sentiment")
    lines.append("| Subreddit | Score | Confidence | n posts | n comments | Theme |")
    lines.append("|-----------|-------|------------|---------|------------|-------|")
    for sent in digest.per_sub_sentiment:
        lines.append(
            f"| {sent.subreddit} | {sent.score:.2f} | {sent.confidence:.2f}"
            f" | {sent.n_posts} | {sent.n_comments} | {sent.theme} |"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json(
    path: Path,
    digest: Digest,
    posts_by_id: dict[str, RawPost],
    summaries_by_id: dict[str, PostSummary],
) -> None:
    seen: set[str] = set()
    post_entries: list[dict] = []

    notable_ids = [n.post_id for n in digest.notable_posts]
    all_ids = notable_ids + [pid for pid in summaries_by_id if pid not in notable_ids]

    for pid in all_ids:
        if pid in seen:
            continue
        seen.add(pid)
        post = posts_by_id.get(pid)
        summary = summaries_by_id.get(pid)
        entry: dict = {}
        if post is not None:
            entry["raw"] = post.model_dump(mode="json")
        if summary is not None:
            entry["summary"] = summary.model_dump(mode="json")
        if entry:
            post_entries.append(entry)

    payload = {
        "meta": {
            "prompt": digest.prompt,
            "generated_utc": digest.generated_utc,
            "subreddits_used": digest.subreddits_used,
            "post_count": digest.post_count,
        },
        "digest": digest.model_dump(mode="json"),
        "posts": post_entries,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, rows: list[SentimentJsonlRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(row.model_dump_json() + "\n")
