"""Pydantic schemas per v1.spec §6."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RawComment(BaseModel):
    id: str
    author: str | None = None
    body: str
    score: int
    created_utc: float
    depth: int
    parent_id: str


class RawPost(BaseModel):
    id: str
    subreddit: str
    title: str
    author: str | None = None
    url: str
    permalink: str
    selftext: str = ""
    score: int
    upvote_ratio: float = 0.0
    num_comments: int = 0
    created_utc: float
    flair: str | None = None
    is_self: bool = False
    top_comments: list[RawComment] = Field(default_factory=list)


class PostSummary(BaseModel):
    post_id: str
    one_sentence: str
    three_bullets: list[str] = Field(min_length=3, max_length=3)
    key_quotes: list[str] = Field(default_factory=list, max_length=3)
    sentiment: Literal["positive", "neutral", "negative", "mixed"]
    topics: list[str] = Field(min_length=1, max_length=5)
    relevance_to_prompt: float = 0.0


class SubSentiment(BaseModel):
    subreddit: str
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    n_posts: int
    n_comments: int
    theme: str


class NotablePost(BaseModel):
    post_id: str
    why_notable: str


class Digest(BaseModel):
    prompt: str
    generated_utc: str
    subreddits_used: list[str]
    post_count: int
    themes: list[str] = Field(default_factory=list)
    narrative: str
    notable_posts: list[NotablePost] = Field(default_factory=list)
    per_sub_sentiment: list[SubSentiment] = Field(default_factory=list)


class PromptRow(BaseModel):
    """Row in `prompts` table."""

    prompt_hash: str
    prompt_text: str
    ran_at: str
    subreddits: list[str]
    post_ids: list[str]
    digest_md_path: str | None = None
    digest_json: str  # serialized Digest


class SentimentJsonlRow(BaseModel):
    """One row appended to <emit_dir>/<TICKER>.jsonl when --ticker is set."""

    ts: str
    ticker: str
    sub: str
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    n_posts: int
    n_comments: int
    theme: str
    prompt: str
    learning_version: str = "v1"
    model: str
