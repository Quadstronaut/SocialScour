import json
import os
from datetime import datetime
from .schema import ScrapeResult

def write_json(data: ScrapeResult, path: str):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data.model_dump(), f, indent=2, ensure_ascii=False)

def write_markdown(data: ScrapeResult, path: str):
    digest = data.digest
    posts = data.posts
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f"# r/{digest.subreddit} — {digest.window} — {datetime.utcnow().strftime('%Y-%m-%d')}\n\n")
        f.write(f"{digest.narrative}\n\n")
        f.write(f"**Themes:** {', '.join(digest.themes)}\n\n")
        f.write("## Notable posts\n")
        
        for post_data in posts[:5]:  # Top 5 notable posts
            post = post_data['raw']
            summary = post_data['summary']
            
            f.write(f"- **{post.title}** (score {post.score}, {post.num_comments} comments) — {summary.one_sentence}\n")
            f.write(f"  {summary.one_sentence}\n")
            for bullet in summary.three_bullets:
                f.write(f"  - {bullet}\n")
            for quote in summary.key_quotes[:2]:
                f.write(f"  > {quote}\n")
            f.write(f"  [link]({post.permalink})\n\n")
