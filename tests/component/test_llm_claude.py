"""Tests for ClaudeClient subprocess wrapper."""
from __future__ import annotations

import subprocess

import pytest

from social_scraper.core.llm.claude import ClaudeClient, ClaudeError


pytestmark = pytest.mark.component


def test_summarize_calls_claude_p(mocker):
    run = mocker.patch(
        "social_scraper.core.llm.claude.subprocess.run",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="OK\n", stderr=""),
    )
    client = ClaudeClient()
    out = client.summarize("text to summarize", "prompt context")
    assert out == "OK"
    args, kwargs = run.call_args
    cmd = args[0]
    assert cmd[0] == "claude"
    assert "-p" in cmd


def test_summarize_raises_on_nonzero(mocker):
    mocker.patch(
        "social_scraper.core.llm.claude.subprocess.run",
        return_value=subprocess.CompletedProcess(args=[], returncode=2, stdout="", stderr="boom"),
    )
    client = ClaudeClient()
    with pytest.raises(ClaudeError):
        client.summarize("x", "y")


def test_summarize_raises_when_claude_not_installed(mocker):
    mocker.patch(
        "social_scraper.core.llm.claude.subprocess.run",
        side_effect=FileNotFoundError(),
    )
    client = ClaudeClient()
    with pytest.raises(ClaudeError):
        client.summarize("x", "y")
