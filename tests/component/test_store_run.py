"""Tests for store.run."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from social_scraper.core.schema import RawPost, RunMeta, SourceKind
from social_scraper.core.store.run import RunWriter, slugify


pytestmark = pytest.mark.component


def test_slugify_basics():
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("AI/ML  trends — 2026") == "ai-ml-trends-2026"
    assert len(slugify("x" * 200)) <= 60


def test_run_writer_creates_layout(tmp_path):
    started = datetime(2026, 5, 11, 14, 22, 3, tzinfo=timezone.utc)
    writer = RunWriter(
        root=tmp_path,
        topic="vibecoding",
        sources=[SourceKind.reddit, SourceKind.hn],
        window_days=30,
        model="qwen3-coder:30b",
        summarizer="ollama",
        started=started,
    )
    assert writer.run_dir.name == "vibecoding_2026-05-11T14-22-03Z"
    assert (writer.run_dir / "raw").is_dir()
    assert (writer.run_dir / "summary").is_dir()
    assert (writer.run_dir / "meta.json").is_file()
    meta = json.loads((writer.run_dir / "meta.json").read_text())
    assert meta["topic"] == "vibecoding"
    assert meta["slug"] == "vibecoding"


def test_run_writer_appends_raw_jsonl(tmp_path):
    started = datetime(2026, 5, 11, tzinfo=timezone.utc)
    writer = RunWriter(
        root=tmp_path, topic="x", sources=[SourceKind.reddit],
        window_days=7, model="m", summarizer="ollama", started=started,
    )
    post = RawPost(
        source=SourceKind.reddit, id="abc", url="u", title="t",
        created_utc=1.0, subreddit="test",
    )
    writer.write_raw(SourceKind.reddit, [post])
    line = (writer.run_dir / "raw" / "reddit.jsonl").read_text().strip()
    assert json.loads(line)["id"] == "abc"


def test_run_writer_writes_summary_and_finalizes(tmp_path):
    started = datetime(2026, 5, 11, tzinfo=timezone.utc)
    writer = RunWriter(
        root=tmp_path, topic="x", sources=[SourceKind.reddit],
        window_days=7, model="m", summarizer="ollama", started=started,
    )
    writer.write_summary_md("# Summary\n\nSome text.")
    writer.add_warning("rank_fallback_used")
    finished = datetime(2026, 5, 11, 0, 1, 0, tzinfo=timezone.utc)
    writer.finalize(finished=finished)
    meta = json.loads((writer.run_dir / "meta.json").read_text())
    assert meta["finished_utc"] == "2026-05-11T00:01:00Z"
    assert "rank_fallback_used" in meta["warnings"]
    summary = (writer.run_dir / "summary" / "summary.md").read_text()
    assert summary.startswith("# Summary")
