import os
import time
import random
from typing import List, Optional, Dict, Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .schema import RawPost, RawComment

# Rate limiting
MIN_DELAY = 2.0
JITTER = 0.5
REQUESTS_PER_MINUTE = 30
TOKENS_PER_MINUTE = REQUESTS_PER_MINUTE
tokens = TOKENS_PER_MINUTE
last_refill = time.time()

def rate_limit():
    global tokens, last_refill
    now = time.time()
    # Refill tokens
    tokens += (now - last_refill) * (TOKENS_PER_MINUTE / 60)
    tokens = min(tokens, TOKENS_PER_MINUTE)
    last_refill = now
    
    if tokens < 1:
        sleep_time = (1 - tokens) / (TOKENS_PER_MINUTE / 60) + random.uniform(-JITTER, JITTER)
        time.sleep(max(0, sleep_time))
        tokens = 0
    else:
        tokens -= 1

def get_user_agent():
    return os.environ.get("REDDIT_USER_AGENT", "reddit-scraper/0.1 (by /u/anonymous; +https://github.com/local)")

client = httpx.Client(
    http2=True,
    timeout=30.0,
    follow_redirects=True,
    headers={
        "User-Agent": get_user_agent(),
        "Accept": "application/json",
    }
)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=(
        retry_if_exception_type(httpx.HTTPStatusError) &
        (lambda exc: exc.response.status_code in [429, 500, 502, 503, 504])
    ) | retry_if_exception_type(httpx.TransportError),
)
def fetch_listing(subreddit: str, listing: str, time_filter: str, limit: int, after: Optional[str] = None) -> Dict[str, Any]:
    rate_limit()
    url = f"https://www.reddit.com/r/{subreddit}/{listing}.json"
    params = {
        "t": time_filter,
        "limit": limit,
    }
    if after:
        params["after"] = after
    
    response = client.get(url, params=params)
    
    # Check for HTML response (403)
    if response.status_code == 403 or response.text.startswith("<"):
        raise httpx.HTTPStatusError(
            "Reddit returned 403 — User-Agent likely flagged. Try a different UA or wait a few hours.",
            request=response.request,
            response=response
        )
    
    response.raise_for_status()
    return response.json()

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=(
        retry_if_exception_type(httpx.HTTPStatusError) &
        (lambda exc: exc.response.status_code in [429, 500, 502, 503, 504])
    ) | retry_if_exception_type(httpx.TransportError),
)
def fetch_post_comments(subreddit: str, post_id: str, limit: int = 100, depth: int = 1) -> Dict[str, Any]:
    rate_limit()
    url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json"
    params = {
        "limit": limit,
        "depth": depth,
    }
    
    response = client.get(url, params=params)
    
    # Check for HTML response (403)
    if response.status_code == 403 or response.text.startswith("<"):
        raise httpx.HTTPStatusError(
            "Reddit returned 403 — User-Agent likely flagged. Try a different UA or wait a few hours.",
            request=response.request,
            response=response
        )
    
    response.raise_for_status()
    return response.json()

def fetch_posts_and_comments(subreddit: str, post_ids: List[str], comments_limit: int = 10) -> List[RawPost]:
    posts = []
    for post_id in post_ids:
        try:
            response_data = fetch_post_comments(subreddit, post_id, comments_limit)
            post_data = response_data[0]["data"]["children"][0]["data"]
            comments_data = response_data[1]["data"]["children"]
            
            # Extract post data
            post = RawPost(
                id=post_data["id"],
                subreddit=post_data["subreddit"],
                title=post_data["title"],
                author=post_data["author"] or "[deleted]",
                url=post_data["url"],
                permalink=f"https://www.reddit.com{post_data['permalink']}",
                selftext=post_data.get("selftext", ""),
                score=post_data["score"],
                upvote_ratio=post_data["upvote_ratio"],
                num_comments=post_data["num_comments"],
                created_utc=post_data["created_utc"],
                flair=post_data.get("link_flair_text"),
                is_self=post_data["is_self"],
                top_comments=[]
            )
            
            # Extract comments
            comments = []
            for child in comments_data:
                if child["kind"] == "t1":
                    comment_data = child["data"]
                    comment = RawComment(
                        id=comment_data["id"],
                        author=comment_data["author"] or "[deleted]",
                        body=comment_data["body"],
                        score=comment_data["score"],
                        created_utc=comment_data["created_utc"],
                        depth=comment_data["depth"],
                        parent_id=comment_data["parent_id"].replace("t3_", "")
                    )
                    comments.append(comment)
            
            # Sort comments by score and take top N
            comments.sort(key=lambda x: x.score, reverse=True)
            post.top_comments = comments[:comments_limit]
            
            posts.append(post)
        except Exception as e:
            print(f"Error fetching post {post_id}: {e}")
            continue
    
    return posts
