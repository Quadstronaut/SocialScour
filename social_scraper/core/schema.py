"""Pydantic models shared across the scraper."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SourceKind(str, Enum):
    reddit = "reddit"
    hn = "hn"
    indiehackers = "indiehackers"
    google_trends = "google_trends"


class RawComment(BaseModel):
    id: str
    author: Optional[str] = None
    body: str
    score: int
    created_utc: float
    depth: int = 0
    parent_id: Optional[str] = None


class RawPost(BaseModel):
    source: SourceKind
    id: str
    url: str
    title: str
    author: Optional[str] = None
    body: str = ""
    score: int = 0
    num_comments: int = 0
    created_utc: float
    # Reddit-specific (optional everywhere else)
    subreddit: Optional[str] = None
    permalink: Optional[str] = None
    upvote_ratio: Optional[float] = None
    is_self: Optional[bool] = None
    flair: Optional[str] = None
    top_comments: list[RawComment] = Field(default_factory=list)


class PostSummary(BaseModel):
    post_id: str
    source: SourceKind
    summary: str
    themes: list[str] = Field(default_factory=list)
    relevance_to_prompt: float = Field(ge=0.0, le=1.0, default=0.0)


class SourceSentiment(BaseModel):
    source: SourceKind
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    n_posts: int = 0
    n_comments: int = 0
    theme: str = ""


class NotablePost(BaseModel):
    post_id: str
    source: SourceKind
    url: str
    title: str
    why: str


class Digest(BaseModel):
    prompt: str
    generated_utc: str
    sources_used: list[SourceKind]
    item_count: int
    themes: list[str] = Field(default_factory=list)
    narrative: str
    notable_posts: list[NotablePost] = Field(default_factory=list)
    per_source_sentiment: list[SourceSentiment] = Field(default_factory=list)


class RunMeta(BaseModel):
    topic: str
    slug: str
    window_days: int
    sources: list[SourceKind]
    model: str
    summarizer: str  # "ollama" | "claude"
    started_utc: str
    finished_utc: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    blocked_sources: list[SourceKind] = Field(default_factory=list)
