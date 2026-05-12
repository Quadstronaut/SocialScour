"""Tests for the scrape CLI."""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner


pytestmark = pytest.mark.workflow


def test_cli_help():
    from social_scraper.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "ask" in result.stdout
    assert "discover" in result.stdout


def test_cli_timeline_missing_topic(tmp_path):
    from social_scraper.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["timeline", "nonexistent", "--data-root", str(tmp_path)])
    assert result.exit_code != 0
    assert "no timeline" in result.stdout.lower() or "no timeline" in result.stderr.lower()


def test_cli_timeline_existing(tmp_path):
    topic_dir = tmp_path / "topics" / "x"
    topic_dir.mkdir(parents=True)
    (topic_dir / "timeline.md").write_text("# x\n\n## 2026-05-11\n\nverdict\n")
    from social_scraper.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["timeline", "x", "--data-root", str(tmp_path)])
    assert result.exit_code == 0
    assert "verdict" in result.stdout
