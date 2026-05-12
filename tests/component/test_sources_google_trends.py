"""Tests for GoogleTrendsClient (TrendsPyG wrapper)."""
from __future__ import annotations

import pytest

from social_scraper.core.sources.google_trends import GoogleTrendsClient, TrendsResult


pytestmark = pytest.mark.component


class _FakeBackend:
    def __init__(self):
        self.calls = []

    def interest_over_time(self, kw_list, timeframe, geo):
        self.calls.append(("iot", kw_list, timeframe, geo))
        return {
            "dates": ["2026-04-12", "2026-04-13"],
            "values": {kw_list[0]: [50, 80]},
        }

    def related_queries(self, kw_list):
        self.calls.append(("rq", kw_list))
        return {kw_list[0]: {"top": ["q1", "q2", "q3"]}}


def test_interest_over_time_uses_backend():
    fake = _FakeBackend()
    client = GoogleTrendsClient(backend=fake)
    out: TrendsResult = client.snapshot("vibecoding", window_days=30, geo="")
    assert out.keyword == "vibecoding"
    assert out.geo == ""
    assert out.interest_over_time["values"]["vibecoding"] == [50, 80]
    assert out.top_related == ["q1", "q2", "q3"]
    assert fake.calls[0][0] == "iot"
    assert fake.calls[1][0] == "rq"
