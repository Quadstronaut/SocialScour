"""Hacker News Algolia search client."""
from __future__ import annotations

import time
from typing import Optional

import httpx

from social_scraper.core.schema import RawPost, SourceKind


_ALGOLIA = "https://hn.algolia.com/api/v1/search"


class HNClient:
    def __init__(self, http_client: Optional[httpx.Client] = None, timeout: float = 30.0) -> None:
        self._http = http_client or httpx.Client(timeout=timeout)
        self._owns_http = http_client is None

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def search(self, query: str, window_days: int = 30, limit: int = 50) -> list[RawPost]:
        since_i = int(time.time()) - window_days * 86400
        params = {
            "query": query,
            "tags": "(story,comment)",
            "numericFilters": f"created_at_i>{since_i}",
            "hitsPerPage": min(limit, 100),
        }
        resp = self._http.get(_ALGOLIA, params=params)
        resp.raise_for_status()
        data = resp.json()
        out: list[RawPost] = []
        for hit in data.get("hits", []):
            tags = hit.get("_tags", [])
            if "story" in tags:
                out.append(self._story(hit))
            elif "comment" in tags:
                out.append(self._comment_as_post(hit))
        return out[:limit]

    def _story(self, h: dict) -> RawPost:
        oid = h.get("objectID", "")
        return RawPost(
            source=SourceKind.hn,
            id=f"story:{oid}",
            url=h.get("url") or f"https://news.ycombinator.com/item?id={oid}",
            title=h.get("title", ""),
            author=h.get("author"),
            body=h.get("story_text", "") or "",
            score=int(h.get("points") or 0),
            num_comments=int(h.get("num_comments") or 0),
            created_utc=float(h.get("created_at_i") or 0),
        )

    def _comment_as_post(self, h: dict) -> RawPost:
        oid = h.get("objectID", "")
        story_id = h.get("story_id", "")
        return RawPost(
            source=SourceKind.hn,
            id=f"comment:{oid}",
            url=f"https://news.ycombinator.com/item?id={oid}",
            title=(h.get("story_title") or "(comment)")[:120],
            author=h.get("author"),
            body=h.get("comment_text", "") or "",
            score=int(h.get("points") or 0),
            num_comments=0,
            created_utc=float(h.get("created_at_i") or 0),
            permalink=f"https://news.ycombinator.com/item?id={story_id}",
        )
