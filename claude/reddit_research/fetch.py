"""Rate-limited Reddit JSON API client (no auth, no PRAW)."""
from __future__ import annotations

import os
import random
import time

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from reddit_research.schema import RawComment, RawPost

DEFAULT_USER_AGENT: str = os.environ.get(
    "REDDIT_USER_AGENT",
    "reddit-research/0.1 (by /u/anonymous; +https://github.com/local)",
)

_BASE = "https://www.reddit.com"
_NO_TIME_FILTER = {"hot", "new", "rising"}


class RedditBlockedError(Exception):
    pass


def make_client() -> httpx.Client:
    return httpx.Client(
        http2=True,
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
    )


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return isinstance(exc, httpx.TransportError)


class RedditClient:
    def __init__(
        self,
        client: httpx.Client,
        user_agent: str = DEFAULT_USER_AGENT,
        min_interval: float = 2.0,
        jitter: float = 0.5,
    ) -> None:
        self._client = client
        self._user_agent = user_agent
        self._min_interval = min_interval
        self._jitter = jitter
        self._last_request_at: float = 0.0

    def _throttle(self) -> None:
        if self._min_interval <= 0.0 and self._jitter <= 0.0:
            return
        elapsed = time.monotonic() - self._last_request_at
        wait = self._min_interval + random.uniform(0, self._jitter) - elapsed
        if wait > 0:
            time.sleep(wait)

    def _get(self, url: str, **params) -> dict:
        self._throttle()

        @retry(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            reraise=True,
        )
        def _do() -> dict:
            resp = self._client.get(url, params=params)
            self._last_request_at = time.monotonic()
            if resp.status_code == 403:
                raise RedditBlockedError(
                    "Reddit returned 403 — User-Agent likely flagged. "
                    "Try a different UA or wait a few hours."
                )
            resp.raise_for_status()
            text = resp.text.lstrip()
            if text.startswith("<"):
                raise RedditBlockedError(
                    "Reddit returned 403 — User-Agent likely flagged. "
                    "Try a different UA or wait a few hours."
                )
            return resp.json()

        return _do()

    def search_subreddits(self, query: str, limit: int = 25) -> list[dict]:
        data = self._get(f"{_BASE}/subreddits/search.json", q=query, limit=limit)
        return [c["data"] for c in data["data"]["children"]]

    def about_subreddit(self, name: str) -> dict | None:
        try:
            data = self._get(f"{_BASE}/r/{name}/about.json")
            return data["data"]
        except (RedditBlockedError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, RedditBlockedError):
                return None
            if exc.response.status_code in {403, 404}:
                return None
            raise

    def fetch_listing(
        self,
        sub: str,
        listing: str = "top",
        time_filter: str = "month",
        limit: int = 25,
        after: str | None = None,
    ) -> tuple[list[RawPost], str | None]:
        params: dict = {"limit": limit}
        if listing not in _NO_TIME_FILTER:
            params["t"] = time_filter
        if after:
            params["after"] = after
        raw = self._get(f"{_BASE}/r/{sub}/{listing}.json", **params)
        children = raw["data"]["children"]
        posts = [_parse_post(c["data"]) for c in children if c["kind"] == "t3"]
        cursor: str | None = raw["data"]["after"]
        return posts, cursor

    def fetch_comments(self, sub: str, post_id: str, limit: int = 10) -> RawPost:
        raw = self._get(
            f"{_BASE}/r/{sub}/comments/{post_id}.json", limit=limit, depth=1
        )
        post_data = raw[0]["data"]["children"][0]["data"]
        post = _parse_post(post_data)
        comments: list[RawComment] = []
        for child in raw[1]["data"]["children"]:
            if child["kind"] != "t1":
                continue
            d = child["data"]
            if d.get("depth", 0) != 0:
                continue
            comments.append(_parse_comment(d))
        post.top_comments = sorted(comments, key=lambda c: c.score, reverse=True)
        return post


def _parse_post(d: dict) -> RawPost:
    return RawPost(
        id=d["id"],
        subreddit=d["subreddit"],
        title=d["title"],
        author=d.get("author"),
        url=d["url"],
        permalink=f"https://www.reddit.com{d['permalink']}",
        selftext=d.get("selftext", ""),
        score=d["score"],
        upvote_ratio=d.get("upvote_ratio", 0.0),
        num_comments=d.get("num_comments", 0),
        created_utc=float(d["created_utc"]),
        flair=d.get("link_flair_text"),
        is_self=bool(d.get("is_self", False)),
    )


def _parse_comment(d: dict) -> RawComment:
    raw_parent = d.get("parent_id", "")
    parent_id = raw_parent.removeprefix("t3_")
    return RawComment(
        id=d["id"],
        author=d.get("author"),
        body=d.get("body", ""),
        score=d.get("score", 0),
        created_utc=float(d.get("created_utc", 0.0)),
        depth=d.get("depth", 0),
        parent_id=parent_id,
    )
