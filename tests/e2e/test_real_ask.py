"""End-to-end test against real Ollama + real Reddit/HN/IH/Trends.

Run with: pytest tests/e2e --e2e -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from social_scraper.core.llm.ollama import OllamaClient
from social_scraper.core.pipeline.ask import AskConfig, run_ask
from social_scraper.core.schema import SourceKind
from social_scraper.core.sources.google_trends import GoogleTrendsClient
from social_scraper.core.sources.hn import HNClient
from social_scraper.core.sources.indiehackers import IndieHackersClient
from social_scraper.core.sources.reddit import RedditClient, make_client


pytestmark = pytest.mark.e2e


def test_known_good_topic(tmp_path):
    llm = OllamaClient(model="qwen3-coder:30b", timeout=600.0)
    assert llm.ping(), "Ollama unreachable — start `ollama serve` and pull qwen3-coder:30b"

    cfg = AskConfig(
        topic="local LLM coding",
        window_days=7,
        sources=[SourceKind.reddit, SourceKind.hn, SourceKind.indiehackers, SourceKind.google_trends],
        model="qwen3-coder:30b",
        summarizer="ollama",
        data_root=tmp_path / "data",
        cache_path=tmp_path / "cache" / "c.sqlite",
        reputation_path=tmp_path / "cache" / "rep.json",
        top_k=5,
    )
    result = run_ask(
        cfg,
        llm=llm,
        reddit=RedditClient(make_client()),
        hn=HNClient(),
        indiehackers=IndieHackersClient(),
        google_trends=GoogleTrendsClient(),
    )
    summary_path: Path = result["summary_path"]
    text = summary_path.read_text(encoding="utf-8")
    assert len(text) > 200, f"summary too short ({len(text)} chars)"

    meta_path = result["run_dir"] / "meta.json"
    meta = json.loads(meta_path.read_text())
    assert "rank_fallback_used" not in meta["warnings"], f"rank fell back: {meta['warnings']}"
