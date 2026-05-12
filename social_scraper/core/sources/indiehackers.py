"""IndieHackers BeautifulSoup scraper."""
from __future__ import annotations

import time
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from social_scraper.core.schema import RawPost, SourceKind


_BASE = "https://www.indiehackers.com"


class IndieHackersClient:
    def __init__(
        self,
        http_client: Optional[httpx.Client] = None,
        throttle_s: float = 3.0,
        timeout: float = 30.0,
    ) -> None:
        self._http = http_client or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "social-scraper/0.2 (research)"},
        )
        self._owns_http = http_client is None
        self._throttle_s = throttle_s
        self._last_request_at = 0.0

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def _throttle(self) -> None:
        if self._throttle_s <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        wait = self._throttle_s - elapsed
        if wait > 0:
            time.sleep(wait)

    def fetch_listing(self, category: str, limit: int = 20) -> list[RawPost]:
        self._throttle()
        resp = self._http.get(f"{_BASE}/{category}")
        self._last_request_at = time.monotonic()
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        posts: list[RawPost] = []
        for item in soup.select(".feed-item")[:limit]:
            content = item.select_one(".feed-item__content")
            if not content:
                continue
            link = content.select_one("a")
            if not link:
                continue
            href = link.get("href", "")
            title = link.get_text(strip=True)
            author_el = content.select_one(".feed-item__author")
            author = author_el.get_text(strip=True).lstrip("@") if author_el else None
            score_el = content.select_one(".feed-item__upvotes")
            score = int(score_el.get_text(strip=True)) if score_el and score_el.get_text(strip=True).isdigit() else 0
            posts.append(RawPost(
                source=SourceKind.indiehackers,
                id=href.strip("/").split("/")[-1] or title[:40],
                url=f"{_BASE}{href}" if href.startswith("/") else href,
                title=title,
                author=author,
                score=score,
                num_comments=0,
                created_utc=0.0,
            ))
        return posts
