"""Unit tests for reddit_research.filter."""
import pytest

from reddit_research.filter import filter_comments, signal_density
from reddit_research.schema import RawComment


def _comment(**kwargs) -> RawComment:
    defaults = dict(
        id="abc",
        author="someuser",
        body="x" * 130,
        score=10,
        created_utc=0.0,
        depth=0,
        parent_id="t3_post1",
    )
    defaults.update(kwargs)
    return RawComment(**defaults)


def test_drops_automoderator():
    comments = [_comment(author="AutoModerator")]
    assert filter_comments(comments) == []


def test_drops_short_body():
    comments = [_comment(body="too short")]
    assert filter_comments(comments) == []


def test_drops_low_score():
    comments = [_comment(score=4)]
    assert filter_comments(comments) == []


def test_drops_depth_nonzero():
    comments = [_comment(depth=1)]
    assert filter_comments(comments) == []


def test_keeps_only_top_max_keep_by_score():
    comments = [_comment(id=str(i), score=i) for i in range(20)]
    result = filter_comments(comments, max_keep=5)
    assert len(result) == 5
    scores = [c.score for c in result]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 19
