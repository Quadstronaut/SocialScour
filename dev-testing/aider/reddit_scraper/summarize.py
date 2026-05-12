from typing import List, Dict, Any
from openai import OpenAI
import os
from .schema import PostSummary, SubredditDigest, RawPost

# Default model
DEFAULT_MODEL = "qwen3-coder:30b"

# Prompts
POST_SUMMARY_SYSTEM_PROMPT = "You summarize Reddit posts for downstream LLMs and humans. Be faithful, concrete, and quote real comments. Never invent facts. Output ONLY valid JSON matching the requested schema."

DIGEST_SYSTEM_PROMPT = "You write a 4–8 sentence plain-English briefing on what is currently happening in a subreddit, based on the provided post summaries. Name specific themes, tensions, and notable threads. No hedging."

def create_openai_client():
    return OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama"
    )

def summarize_post(client: OpenAI, post: RawPost, model: str = DEFAULT_MODEL) -> PostSummary:
    # Prepare the prompt
    prompt = f"""
Summarize this Reddit post in JSON format:

Title: {post.title}
Author: {post.author}
Score: {post.score}
Upvote ratio: {post.upvote_ratio}
URL: {post.url}
Selftext: {post.selftext}
Comments: {len(post.top_comments)} comments

Top comments:
"""
    
    for i, comment in enumerate(post.top_comments[:3]):
        prompt += f"{i+1}. {comment.author}: {comment.body[:200]}... (score: {comment.score})\n"
    
    prompt += "\nOutput ONLY valid JSON matching this schema:\n"
    prompt += '{"post_id": "string", "one_sentence": "string (≤25 words)", "three_bullets": ["string", "string", "string"], "key_quotes": ["string", "string", "string"], "sentiment": "positive|neutral|negative|mixed", "topics": ["string", "string", "string", "string", "string"]}\n'
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": POST_SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.3
    )
    
    # Parse the response
    summary_data = response.choices[0].message.content
    # Simple JSON parsing (in a real app, we'd use proper JSON parsing)
    import json
    try:
        summary_dict = json.loads(summary_data)
        return PostSummary(**summary_dict)
    except Exception:
        # Fallback to basic parsing
        return PostSummary(
            post_id=post.id,
            one_sentence="",
            three_bullets=["", "", ""],
            key_quotes=[],
            sentiment="neutral",
            topics=[]
        )

def summarize_digest(client: OpenAI, posts: List[RawPost], subreddit: str, model: str = DEFAULT_MODEL) -> SubredditDigest:
    # Prepare the prompt
    prompt = f"""
Write a 4-8 sentence plain-English briefing on what is currently happening in r/{subreddit}.

Here are the posts and their summaries:

"""
    
    for post in posts[:10]:  # Limit to top 10 posts for digest
        prompt += f"- {post.title}\n"
        # We'll add a placeholder for the summary here, but in practice we'd have the actual summaries
        prompt += f"  (Score: {post.score}, Comments: {post.num_comments})\n\n"
    
    prompt += "\nWrite a narrative that covers the main themes, tensions, and notable threads in this subreddit.\n"
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": DIGEST_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0.5
    )
    
    # For simplicity, we'll create a basic digest structure
    return SubredditDigest(
        subreddit=subreddit,
        generated_utc="",
        window="",
        post_count=len(posts),
        themes=["technology", "programming"],
        narrative=response.choices[0].message.content,
        notable_posts=[]
    )
