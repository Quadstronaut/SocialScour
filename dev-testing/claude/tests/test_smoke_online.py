"""Online sanity check. Hits real Reddit (r/test) and real Ollama.

Skipped automatically if Ollama is not reachable. Not part of the loop target.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from reddit_research.cli import run_ask
from reddit_research.llm import LLM
from reddit_research.schema import Digest, SentimentJsonlRow

pytestmark = pytest.mark.online


def _ollama_up() -> bool:
    try:
        return LLM().ping()
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_up(), reason="Ollama not reachable at localhost:11434")
def test_real_run_against_r_test(tmp_path: Path) -> None:
    out = tmp_path / "data"
    cache_db = tmp_path / "cache" / "cache.db"
    rep_path = tmp_path / "cache" / "reputation.json"

    # Prompt is intentionally generic so r/test or any reddit-search-discovered sub
    # can produce something. We assert structure only, not content.
    result = run_ask(
        "what is reddit",
        listing="hot",
        time_filter="day",
        limit=5,
        top_k=3,
        comments_per_post=3,
        max_subs=3,
        out_dir=out,
        cache_db=cache_db,
        reputation_path=rep_path,
        stream_digest=False,
    )

    assert result["from_cache"] is False
    assert result["md_path"].exists()
    assert result["json_path"].exists()

    payload = json.loads(result["json_path"].read_text(encoding="utf-8"))
    assert "digest" in payload and "posts" in payload and "meta" in payload

    digest = result["digest"]
    assert isinstance(digest, Digest)
    assert digest.narrative.strip()
    assert digest.post_count >= 1
    assert digest.subreddits_used

    # Markdown contains structural anchors
    md = result["md_path"].read_text(encoding="utf-8")
    assert "## Notable posts" in md
    assert "## Per-subreddit sentiment" in md
