"""In-process tests for the MCP server tools.

These call the *implementations* directly (not via the MCP transport) to verify
the return-shape contract — paths only on ask/discover, content only on
read_summary/read_timeline.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from social_scraper.mcp_server import (
    _impl_ask,
    _impl_discover,
    _impl_read_summary,
    _impl_read_timeline,
)


pytestmark = pytest.mark.workflow


def test_read_summary_returns_content(tmp_path):
    rd = tmp_path / "run1"
    (rd / "summary").mkdir(parents=True)
    (rd / "summary" / "summary.md").write_text("# hello\n")
    out = _impl_read_summary(str(rd))
    assert out["content"].startswith("# hello")


def test_read_timeline_returns_content(tmp_path):
    (tmp_path / "topics" / "x").mkdir(parents=True)
    (tmp_path / "topics" / "x" / "timeline.md").write_text("# x\n")
    out = _impl_read_timeline("x", data_root=str(tmp_path))
    assert out["content"].startswith("# x")


def test_read_summary_missing_returns_error(tmp_path):
    out = _impl_read_summary(str(tmp_path / "nope"))
    assert "error" in out
