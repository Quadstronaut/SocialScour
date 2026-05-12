"""Unit tests for reddit_research.rank."""
import json

import pytest

from reddit_research.rank import rank_posts
from reddit_research.schema import RawPost


class FakeLLM:
    def __init__(self, response_json: str):
        self.response_json = response_json
        self.calls = []

    def json_call(self, system, user, schema_cls):
        self.calls.append((system, user))
        return schema_cls.model_validate_json(self.response_json)


def _post(id: str, score: int = 0) -> RawPost:
    return RawPost(
        id=id,
        subreddit="testsub",
        title=f"Post {id}",
        url="https://example.com",
        permalink="https://www.reddit.com/r/testsub/comments/abc/",
        score=score,
        created_utc=0.0,
    )


def test_rank_posts_correct_order():
    posts = [_post("a"), _post("b"), _post("c"), _post("d"), _post("e")]
    response = json.dumps(
        {
            "ranked": [
                {"post_id": "a", "relevance": 0.9},
                {"post_id": "b", "relevance": 0.2},
                {"post_id": "c", "relevance": 0.7},
                {"post_id": "d", "relevance": 0.5},
                {"post_id": "e", "relevance": 0.1},
            ]
        }
    )
    llm = FakeLLM(response)
    result = rank_posts(llm, "test prompt", posts, top_k=3)
    assert len(result) == 3
    ids = [p.id for p, _ in result]
    assert ids == ["a", "c", "d"]
    relevances = [r for _, r in result]
    assert relevances == sorted(relevances, reverse=True)


def test_rank_posts_missing_ids_default_to_zero():
    posts = [_post("x", score=100), _post("y", score=1), _post("z", score=1)]
    response = json.dumps(
        {
            "ranked": [
                {"post_id": "y", "relevance": 0.6},
            ]
        }
    )
    llm = FakeLLM(response)
    result = rank_posts(llm, "test prompt", posts, top_k=3)
    assert len(result) == 3
    ids = [p.id for p, _ in result]
    assert ids[0] == "y"
    assert set(ids[1:]) == {"x", "z"}
    for p, rel in result:
        if p.id in ("x", "z"):
            assert rel == 0.0
