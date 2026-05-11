import os
import typer
import time
from datetime import datetime
from typing import List, Optional
from .fetch import fetch_listing, fetch_posts_and_comments
from .summarize import create_openai_client, summarize_post, summarize_digest
from .schema import ScrapeResult, RawPost, SubredditDigest
from .render import write_json, write_markdown

app = typer.Typer()

def run_scrape(
    subreddits: List[str],
    listing: str = "hot",
    time_filter: str = "day",
    limit: int = 25,
    comments: int = 10,
    min_score: int = 0,
    out_dir: str = "data",
    summary_model: str = "qwen3-coder:30b"
):
    # Create output directory
    os.makedirs(out_dir, exist_ok=True)
    
    # Get current timestamp
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    
    # Initialize results
    all_posts = []
    all_digests = []
    
    # Create OpenAI client
    client = create_openai_client()
    
    for subreddit in subreddits:
        print(f"Scraping r/{subreddit}...")
        
        # Fetch posts
        after = None
        collected_posts = []
        
        while len(collected_posts) < limit:
            try:
                response = fetch_listing(subreddit, listing, time_filter, min(limit - len(collected_posts), 100), after)
                posts_data = response["data"]["children"]
                
                # Filter posts by minimum score
                posts_data = [p for p in posts_data if p["data"]["score"] >= min_score]
                
                # Extract post IDs
                post_ids = [p["data"]["id"] for p in posts_data if p["kind"] == "t3"]
                
                # Fetch posts and comments
                posts = fetch_posts_and_comments(subreddit, post_ids, comments)
                collected_posts.extend(posts)
                
                # Check if we have more posts
                after = response["data"].get("after")
                if not after:
                    break
                    
            except Exception as e:
                print(f"Error fetching posts for r/{subreddit}: {e}")
                break
        
        # Limit to requested number of posts
        collected_posts = collected_posts[:limit]
        
        # Summarize posts
        post_summaries = []
        for post in collected_posts:
            try:
                summary = summarize_post(client, post, summary_model)
                post_summaries.append({"raw": post, "summary": summary})
            except Exception as e:
                print(f"Error summarizing post {post.id}: {e}")
                post_summaries.append({"raw": post, "summary": None})
        
        # Summarize digest
        digest = summarize_digest(client, collected_posts, subreddit, summary_model)
        digest.generated_utc = timestamp
        digest.window = f"{listing}/{time_filter}"
        
        # Create result object
        result = ScrapeResult(
            meta={"subreddit": subreddit, "listing": listing, "time_filter": time_filter, "limit": limit},
            posts=post_summaries,
            digest=digest
        )
        
        # Write files
        filename = f"{subreddit}_{listing}_{time_filter}_{timestamp}"
        json_path = os.path.join(out_dir, f"{filename}.json")
        md_path = os.path.join(out_dir, f"{filename}.md")
        
        write_json(result, json_path)
        write_markdown(result, md_path)
        
        all_posts.extend(post_summaries)
        all_digests.append(digest)
    
    # If multiple subreddits, create combined digest
    if len(subreddits) > 1:
        combined_digest = summarize_digest(client, [p['raw'] for p in all_posts], "combined", summary_model)
        combined_digest.generated_utc = timestamp
        combined_digest.window = f"{listing}/{time_filter}"
        combined_digest.post_count = len(all_posts)
        
        # Create combined result
        combined_result = ScrapeResult(
            meta={"subreddits": subreddits, "listing": listing, "time_filter": time_filter, "limit": limit},
            posts=all_posts,
            digest=combined_digest
        )
        
        # Write combined files
        combined_filename = f"combined_{listing}_{time_filter}_{timestamp}"
        json_path = os.path.join(out_dir, f"{combined_filename}.json")
        md_path = os.path.join(out_dir, f"{combined_filename}.md")
        
        write_json(combined_result, json_path)
        write_markdown(combined_result, md_path)

@app.command()
def run(
    subreddits: List[str] = typer.Option(..., "--subreddit", help="Subreddit(s) to scrape"),
    listing: str = typer.Option("hot", "--listing", help="Listing type (hot, new, top, rising)"),
    time_filter: str = typer.Option("day", "--time-filter", help="Time filter (hour, day, week, month, year, all)"),
    limit: int = typer.Option(25, "--limit", help="Number of posts to fetch"),
    comments: int = typer.Option(10, "--comments", help="Number of top comments to fetch per post"),
    min_score: int = typer.Option(0, "--min-score", help="Minimum score threshold"),
    out_dir: str = typer.Option("data", "--out", help="Output directory"),
    summary_model: str = typer.Option("qwen3-coder:30b", "--summary-model", help="Ollama model for summarization")
):
    """Run the Reddit scraper and summarizer."""
    run_scrape(subreddits, listing, time_filter, limit, comments, min_score, out_dir, summary_model)

if __name__ == "__main__":
    app()
