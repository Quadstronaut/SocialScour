"""Tests for store.cache (30-day SQLite key/value)."""
from __future__ import annotations

import time

import pytest

from social_scraper.core.store.cache import LLMCache


pytestmark = pytest.mark.component


def test_put_then_get(tmp_path):
    cache = LLMCache(tmp_path / "c.sqlite")
    cache.put("k1", "value-one")
    assert cache.get("k1") == "value-one"
    cache.close()


def test_get_missing(tmp_path):
    cache = LLMCache(tmp_path / "c.sqlite")
    assert cache.get("nope") is None


def test_expired_entries_purged(tmp_path):
    cache = LLMCache(tmp_path / "c.sqlite", ttl_seconds=0)
    cache.put("k", "v")
    time.sleep(0.05)
    assert cache.get("k") is None


def test_key_helper_stable():
    k1 = LLMCache.make_key("post_id=abc", "model=q", "role=summarize")
    k2 = LLMCache.make_key("role=summarize", "post_id=abc", "model=q")
    assert k1 == k2  # sorted ⇒ order-independent
