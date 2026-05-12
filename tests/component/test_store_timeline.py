"""Tests for store.timeline."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from social_scraper.core.store.timeline import TimelineWriter


pytestmark = pytest.mark.component


def test_first_append_creates_file(tmp_path):
    tw = TimelineWriter(root=tmp_path, slug="vibecoding")
    tw.append(
        when=datetime(2026, 5, 11, 14, 0, 0, tzinfo=timezone.utc),
        run_dir=tmp_path / "runs" / "vibecoding_2026-05-11T14-00-00Z",
        verdict="First paragraph of the narrative.",
    )
    path = tmp_path / "topics" / "vibecoding" / "timeline.md"
    assert path.is_file()
    text = path.read_text()
    assert "# vibecoding" in text
    assert "## 2026-05-11T14:00:00Z" in text
    assert "First paragraph" in text


def test_second_append_keeps_h1_and_adds_new_h2(tmp_path):
    tw = TimelineWriter(root=tmp_path, slug="vibe")
    tw.append(
        when=datetime(2026, 5, 11, tzinfo=timezone.utc),
        run_dir=tmp_path / "runs" / "vibe_2026-05-11T00-00-00Z",
        verdict="V1",
    )
    tw.append(
        when=datetime(2026, 5, 12, tzinfo=timezone.utc),
        run_dir=tmp_path / "runs" / "vibe_2026-05-12T00-00-00Z",
        verdict="V2",
    )
    text = (tmp_path / "topics" / "vibe" / "timeline.md").read_text()
    assert text.count("# vibe\n") == 1
    assert "## 2026-05-11T00:00:00Z" in text
    assert "## 2026-05-12T00:00:00Z" in text
