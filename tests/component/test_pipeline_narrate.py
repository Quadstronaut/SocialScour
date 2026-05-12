"""Tests for pipeline.narrate."""
from __future__ import annotations

import io

import pytest

from social_scraper.core.pipeline.narrate import narrate
from social_scraper.core.schema import PostSummary, SourceKind


pytestmark = pytest.mark.component


class _StubLLM:
    def __init__(self, text: str):
        self._text = text

    def chat_stream(self, system, user):
        for chunk in self._text.split(" "):
            yield chunk + " "


def test_narrate_writes_to_stream_and_returns_full():
    out = io.StringIO()
    llm = _StubLLM("Hello world narrative")
    summaries = [
        PostSummary(post_id="a", source=SourceKind.reddit, summary="s", themes=["t"], relevance_to_prompt=0.5),
    ]
    text = narrate(llm, "prompt", summaries, out_stream=out)
    assert "Hello" in text
    assert "Hello" in out.getvalue()
