"""Google Trends source via trendspy (or pytrends fallback)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class _TrendsBackend(Protocol):
    def interest_over_time(self, kw_list: list[str], timeframe: str, geo: str) -> dict: ...
    def related_queries(self, kw_list: list[str]) -> dict: ...


def _window_to_timeframe(window_days: int) -> str:
    if window_days <= 7:
        return "now 7-d"
    if window_days <= 30:
        return "today 1-m"
    if window_days <= 90:
        return "today 3-m"
    return "today 12-m"


@dataclass
class TrendsResult:
    keyword: str
    geo: str
    window_days: int
    interest_over_time: dict
    top_related: list[str]


class _DefaultBackend:
    def __init__(self) -> None:
        try:
            import trendspy as _ts  # type: ignore[import-untyped]
            self._impl = _ts.Trends()
            self._kind = "trendspy"
        except ImportError:
            from pytrends.request import TrendReq  # type: ignore[import-untyped]
            self._impl = TrendReq(hl="en-US", tz=0)
            self._kind = "pytrends"

    def interest_over_time(self, kw_list, timeframe, geo):
        if self._kind == "pytrends":
            self._impl.build_payload(kw_list, timeframe=timeframe, geo=geo)
            df = self._impl.interest_over_time()
            if df is None or df.empty:
                return {"dates": [], "values": {kw_list[0]: []}}
            return {
                "dates": [str(d) for d in df.index.tolist()],
                "values": {kw_list[0]: df[kw_list[0]].tolist()},
            }
        # trendspy
        df = self._impl.interest_over_time(kw_list, timeframe=timeframe, geo=geo)
        if df is None or df.empty:
            return {"dates": [], "values": {kw_list[0]: []}}
        return {
            "dates": [str(d) for d in df.index.tolist()],
            "values": {kw_list[0]: df[kw_list[0]].tolist()},
        }

    def related_queries(self, kw_list):
        if self._kind == "pytrends":
            self._impl.build_payload(kw_list)
            rq = self._impl.related_queries()
            out = {}
            for kw in kw_list:
                entry = rq.get(kw, {})
                top_df = entry.get("top")
                out[kw] = {"top": top_df["query"].tolist() if top_df is not None else []}
            return out
        return self._impl.related_queries(kw_list)


class GoogleTrendsClient:
    def __init__(self, backend: _TrendsBackend | None = None) -> None:
        self._backend = backend or _DefaultBackend()

    def snapshot(self, keyword: str, window_days: int = 30, geo: str = "") -> TrendsResult:
        tf = _window_to_timeframe(window_days)
        iot = self._backend.interest_over_time([keyword], tf, geo)
        rq = self._backend.related_queries([keyword])
        top = rq.get(keyword, {}).get("top", []) if isinstance(rq, dict) else []
        return TrendsResult(
            keyword=keyword,
            geo=geo,
            window_days=window_days,
            interest_over_time=iot,
            top_related=list(top),
        )
