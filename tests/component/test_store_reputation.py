"""Tests for reputation store (sub pinning per area)."""
from __future__ import annotations

import json

import pytest

from social_scraper.core.store.reputation import Reputation


pytestmark = pytest.mark.component


def test_load_missing_file_returns_empty(tmp_path):
    rep = Reputation(tmp_path / "rep.json")
    assert rep.load() == {"topic_areas": {}}


def test_promote_then_save(tmp_path):
    path = tmp_path / "rep.json"
    rep = Reputation(path)
    rep.load()
    rep.promote("ai_coding", "LocalLLaMA")
    rep.save()
    data = json.loads(path.read_text())
    assert data["topic_areas"]["ai_coding"]["subs"]["LocalLLaMA"]["promoted"] is True


def test_auto_update_records_score(tmp_path):
    rep = Reputation(tmp_path / "rep.json")
    rep.load()
    rep.auto_update("ai_coding", {"LocalLLaMA": {"signal_density": 0.42, "n_posts": 3}})
    rep.save()
    data = json.loads((tmp_path / "rep.json").read_text())
    s = data["topic_areas"]["ai_coding"]["subs"]["LocalLLaMA"]
    assert s["score"] == pytest.approx(0.42)
