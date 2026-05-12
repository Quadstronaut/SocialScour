from typing import List, Optional
from pydantic import BaseModel


class RawComment(BaseModel):
    id: str
    author: str
    body: str
    score: int
    created_utc: float
    depth: int
    parent_id: str


class RawPost(BaseModel):
    id: str
    subreddit: str
    title: str
    author: str
    url: str
    permalink: str
    selftext: str
    score: int
    upvote_ratio: float
    num_comments: int
    created_utc: float
    flair: Optional[str]
    is_self: bool
    top_comments: List[RawComment]


class PostSummary(BaseModel):
    post_id: str
    one_sentence: str
    three_bullets: List[str]
    key_quotes: List[str]
    sentiment: str  # "positive"|"neutral"|"negative"|"mixed"
    topics: List[str]  # 1-5 lowercase tags


class SubredditDigest(BaseModel):
    subreddit: str
    generated_utc: str
    window: str  # listing+time-filter
    post_count: int
    themes: List[str]
    narrative: str
    notable_posts: List[dict]  # {post_id, why_notable}


class ScrapeResult(BaseModel):
    meta: dict
    posts: List[dict]  # {raw: RawPost, summary: PostSummary}
    digest: SubredditDigest
