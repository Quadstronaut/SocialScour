"""Offline smoke test — drives full pipeline with FakeLLM + FakeRedditClient.
Deterministic: no network, no Ollama. Run 3× in a row; must pass every time.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from reddit_research.cache import Cache
from reddit_research.cli import run_ask
from reddit_research.prompts import (
    DISCOVER_SYSTEM,
    POST_SUMMARY_SYSTEM,
    RANKER_SYSTEM,
    SUB_SENTIMENT_SYSTEM,
    TOPIC_AREA_SYSTEM,
)
from reddit_research.reputation import Reputation
from reddit_research.schema import Digest, RawComment, RawPost, SentimentJsonlRow

_FIXTURES = Path(__file__).parent / "fixtures"

_LISTING_DATA = json.loads((_FIXTURES / "listing_r_test.json").read_text(encoding="utf-8"))
_COMMENTS_DATA = json.loads((_FIXTURES / "comments_r_test.json").read_text(encoding="utf-8"))

_KNOWN_SUBS = {"homelab", "netsec", "homenetworking", "crypto"}

_CANNED_SUMMARY = (
    '{"one_sentence":"People use VLANs to segment home networks.",'
    '"three_bullets":["Use a managed switch","Separate IoT","Lock down router admin"],'
    '"key_quotes":["Best $100 I ever spent"],'
    '"sentiment":"positive",'
    '"topics":["networking","security","vlan"]}'
)
_DIGEST_TEXT = (
    "Across the surveyed subreddits, segmentation via VLANs is the dominant theme, "
    "with WPA3 a point of debate and homelab favoring deeper configurability. "
    "Users emphasize router admin hygiene above flashy features."
)


def _parse_post(d: dict, sub: str, idx: int) -> RawPost:
    return RawPost(
        id=f"{sub}_post_{idx}",
        subreddit=sub,
        title=d["title"],
        author=d.get("author"),
        url=d["url"],
        permalink=f"https://www.reddit.com/r/{sub}/comments/{sub}_post_{idx}/",
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
    parent_id = raw_parent.removeprefix("t3_").removeprefix("t1_")
    return RawComment(
        id=d["id"],
        author=d.get("author"),
        body=d.get("body", ""),
        score=d.get("score", 0),
        created_utc=float(d.get("created_utc", 0.0)),
        depth=d.get("depth", 0),
        parent_id=parent_id,
    )


class FakeRedditClient:
    def __init__(self) -> None:
        self.calls: dict[str, int] = {
            "about_subreddit": 0,
            "search_subreddits": 0,
            "fetch_listing": 0,
            "fetch_comments": 0,
        }

    def about_subreddit(self, name: str) -> dict | None:
        self.calls["about_subreddit"] += 1
        if name.lower() in _KNOWN_SUBS:
            return {
                "display_name": name,
                "subscribers": 50000,
                "subreddit_type": "public",
                "over18": False,
            }
        return None

    def search_subreddits(self, query: str, limit: int = 10) -> list[dict]:
        self.calls["search_subreddits"] += 1
        return [
            {
                "display_name": "homeautomation",
                "subscribers": 200000,
                "subreddit_type": "public",
                "over18": False,
            }
        ]

    def fetch_listing(
        self,
        sub: str,
        listing: str = "top",
        time_filter: str = "month",
        limit: int = 25,
        after: str | None = None,
    ) -> tuple[list[RawPost], str | None]:
        self.calls["fetch_listing"] += 1
        children = _LISTING_DATA["data"]["children"]
        posts = [
            _parse_post(c["data"], sub, i)
            for i, c in enumerate(children)
            if c["kind"] == "t3"
        ]
        return posts, None

    def fetch_comments(self, sub: str, post_id: str, limit: int = 10) -> RawPost:
        self.calls["fetch_comments"] += 1
        post_data = _COMMENTS_DATA[0]["data"]["children"][0]["data"]
        post = RawPost(
            id=post_id,
            subreddit=sub,
            title=post_data["title"],
            author=post_data.get("author"),
            url=post_data["url"],
            permalink=f"https://www.reddit.com/r/{sub}/comments/{post_id}/",
            selftext=post_data.get("selftext", ""),
            score=post_data["score"],
            upvote_ratio=post_data.get("upvote_ratio", 0.0),
            num_comments=post_data.get("num_comments", 0),
            created_utc=float(post_data["created_utc"]),
            flair=post_data.get("link_flair_text"),
            is_self=bool(post_data.get("is_self", False)),
        )
        comments: list[RawComment] = []
        for child in _COMMENTS_DATA[1]["data"]["children"]:
            if child["kind"] != "t1":
                continue
            d = child["data"]
            if d.get("depth", 0) != 0:
                continue
            comments.append(_parse_comment(d))
        post.top_comments = sorted(comments, key=lambda c: c.score, reverse=True)
        return post

    def reset_calls(self) -> None:
        for k in self.calls:
            self.calls[k] = 0


class FakeLLM:
    def __init__(self) -> None:
        self.json_calls = 0
        self.text_calls = 0
        self.ping_calls = 0

    def ping(self) -> bool:
        self.ping_calls += 1
        return True

    def json_call(self, system: str, user: str, schema_cls):
        self.json_calls += 1

        if system == POST_SUMMARY_SYSTEM:
            return schema_cls.model_validate_json(_CANNED_SUMMARY)

        if system == DISCOVER_SYSTEM:
            raw = '{"subreddits":["homelab","netsec","homenetworking","crypto","FakeSub404"]}'
            return schema_cls.model_validate_json(raw)

        if system == TOPIC_AREA_SYSTEM:
            raw = '{"area":"home_networking","new":true}'
            return schema_cls.model_validate_json(raw)

        if system == RANKER_SYSTEM:
            pids = re.findall(r'"post_id"\s*:\s*"([^"]+)"', user)
            ranked = [{"post_id": pid, "relevance": 1.0} for pid in pids]
            raw = json.dumps({"ranked": ranked})
            return schema_cls.model_validate_json(raw)

        if system == SUB_SENTIMENT_SYSTEM:
            raw = '{"score":0.55,"confidence":0.7,"theme":"Generally positive but cautious."}'
            return schema_cls.model_validate_json(raw)

        raise ValueError(f"FakeLLM.json_call: unrecognised system prompt:\n{system[:80]!r}")

    def text_call(self, system: str, user: str, stream: bool = False) -> str | Iterator[str]:
        self.text_calls += 1
        text = _DIGEST_TEXT
        if stream:
            third = len(text) // 3
            return iter([text[:third], text[third : third * 2], text[third * 2 :]])
        return text

    def reset_calls(self) -> None:
        self.json_calls = 0
        self.text_calls = 0
        self.ping_calls = 0


_PROMPT = "how do people secure home networks"


@pytest.fixture
def env(tmp_path):
    out = tmp_path / "data"
    cache_db = tmp_path / "cache" / "cache.db"
    rep = tmp_path / "cache" / "reputation.json"
    fake_llm = FakeLLM()
    fake_reddit = FakeRedditClient()
    return SimpleNamespace(
        out=out,
        cache=cache_db,
        rep=rep,
        llm=fake_llm,
        reddit=fake_reddit,
        tmp=tmp_path,
    )


def _run(env, **kwargs) -> dict:
    defaults = dict(
        prompt=_PROMPT,
        out_dir=env.out,
        cache_db=env.cache,
        reputation_path=env.rep,
        llm=env.llm,
        reddit=env.reddit,
        stream_digest=False,
    )
    defaults.update(kwargs)
    return run_ask(**defaults)


def test_pipeline_completes_without_exception(env):
    result = _run(env)
    assert isinstance(result, dict)
    assert result.get("from_cache") is False


def test_artifacts_written(env):
    result = _run(env)
    md = result["md_path"]
    js = result["json_path"]
    assert md is not None and Path(md).exists(), "md file missing"
    assert js is not None and Path(js).exists(), "json file missing"
    assert Path(md).stat().st_size > 100
    assert Path(js).stat().st_size > 100


def test_cache_rows_present(env):
    _run(env)
    cache = Cache(env.cache)
    try:
        prompts = cache.list_prompts(limit=10)
        assert len(prompts) == 1, f"expected 1 prompt row, got {len(prompts)}"
        st = cache.stats()
        assert st["posts"] >= 1, f"expected >=1 post rows, got {st['posts']}"
        assert st["summaries"] >= 1, f"expected >=1 summary rows, got {st['summaries']}"
    finally:
        cache.close()


def test_digest_json_validates(env):
    result = _run(env)
    digest = result["digest"]
    roundtripped = Digest.model_validate(digest.model_dump())
    assert roundtripped.narrative, "narrative is empty"
    assert roundtripped.prompt == _PROMPT


def test_jsonl_emitted_when_ticker_set(env):
    sentiment_dir = env.tmp / "sentiment"
    result = _run(env, ticker="NVDA", emit_sentiment_dir=sentiment_dir)
    jsonl_path = sentiment_dir / "NVDA.jsonl"
    assert jsonl_path.exists(), "NVDA.jsonl not written"
    lines = [l for l in jsonl_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    n_subs = len(result["digest"].subreddits_used)
    assert len(lines) == n_subs, f"expected {n_subs} jsonl rows, got {len(lines)}"
    for line in lines:
        row = json.loads(line)
        SentimentJsonlRow.model_validate(row)


def test_second_run_is_full_cache_hit(env):
    _run(env)

    env.reddit.reset_calls()
    env.llm.reset_calls()

    result2 = _run(env)
    assert result2.get("from_cache") is True, "second run should be a cache hit"
    total_reddit = sum(env.reddit.calls.values())
    assert total_reddit == 0, f"reddit called {total_reddit} times on cache hit"
    assert env.llm.json_calls == 0, f"llm.json_call invoked {env.llm.json_calls} times on cache hit"
    assert env.llm.text_calls == 0, f"llm.text_call invoked {env.llm.text_calls} times on cache hit"


def test_reputation_updated(env):
    _run(env)
    rep = Reputation(env.rep)
    data = rep.load()
    areas = data.get("topic_areas", {})
    assert "home_networking" in areas, f"area 'home_networking' not in reputation; found: {list(areas)}"
    subs = areas["home_networking"].get("subs", {})
    assert subs, "no subs recorded in home_networking area"
    scores = {sub: meta.get("score", 0) for sub, meta in subs.items()}
    assert any(v > 0 for v in scores.values()), (
        f"expected at least one sub with score > 0; got {scores}"
    )
