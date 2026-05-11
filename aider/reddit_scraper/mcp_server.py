import json
import os
import sys
from pathlib import Path
from mcp import Server, StdioTransport
from mcp.types import (
    Tool,
    ToolResult,
    ToolCall,
    TextContent,
    ImageContent,
    Content,
    ToolResultContent,
    ToolResultError,
)
from .schema import ScrapeResult

# Tools
async def list_runs():
    """List available scrape runs."""
    data_dir = Path("data")
    if not data_dir.exists():
        return []
    
    files = [f for f in data_dir.iterdir() if f.is_file() and f.suffix == ".json"]
    runs = []
    for file in files:
        try:
            with open(file, 'r') as f:
                data = json.load(f)
                runs.append({
                    "path": str(file),
                    "subreddit": data.get("meta", {}).get("subreddit", "unknown"),
                    "timestamp": file.name.split("_")[-1].replace(".json", ""),
                    "listing": data.get("meta", {}).get("listing", "unknown"),
                    "time_filter": data.get("meta", {}).get("time_filter", "unknown")
                })
        except Exception:
            continue
    return runs

async def get_digest(subreddit: str, latest: bool = True):
    """Get the digest for a subreddit."""
    data_dir = Path("data")
    if not data_dir.exists():
        return None
    
    # Find the latest file for this subreddit
    files = [f for f in data_dir.iterdir() if f.is_file() and f.suffix == ".json" and subreddit in f.name]
    
    if not files:
        return None
    
    # Sort by timestamp
    files.sort(key=lambda x: x.name)
    
    if latest:
        file = files[-1]
    else:
        file = files[0]
    
    try:
        with open(file, 'r') as f:
            data = json.load(f)
            return data.get("digest")
    except Exception:
        return None

async def search_posts(subreddit: str = None, query: str = "", limit: int = 10):
    """Search posts by title or summary."""
    data_dir = Path("data")
    if not data_dir.exists():
        return []
    
    # Find files for this subreddit or all
    if subreddit:
        files = [f for f in data_dir.iterdir() if f.is_file() and f.suffix == ".json" and subreddit in f.name]
    else:
        files = [f for f in data_dir.iterdir() if f.is_file() and f.suffix == ".json"]
    
    results = []
    for file in files:
        try:
            with open(file, 'r') as f:
                data = json.load(f)
                for post_data in data.get("posts", []):
                    post = post_data.get("raw", {})
                    summary = post_data.get("summary", {})
                    
                    # Check if query matches title or summary
                    if (query.lower() in post.get("title", "").lower() or 
                        query.lower() in summary.get("one_sentence", "").lower()):
                        results.append(summary)
                        if len(results) >= limit:
                            break
        except Exception:
            continue
    
    return results[:limit]

async def get_post(post_id: str):
    """Get a specific post by ID."""
    data_dir = Path("data")
    if not data_dir.exists():
        return None
    
    # Find all JSON files
    files = [f for f in data_dir.iterdir() if f.is_file() and f.suffix == ".json"]
    
    for file in files:
        try:
            with open(file, 'r') as f:
                data = json.load(f)
                for post_data in data.get("posts", []):
                    post = post_data.get("raw", {})
                    if post.get("id") == post_id:
                        return post_data
        except Exception:
            continue
    
    return None

# MCP Server
async def main():
    server = Server("reddit-scraper-mcp")
    
    @server.tool
    async def list_runs_tool() -> ToolResult:
        runs = await list_runs()
        return ToolResult(
            content=[TextContent(text=json.dumps(runs, indent=2))]
        )
    
    @server.tool
    async def get_digest_tool(subreddit: str, latest: bool = True) -> ToolResult:
        digest = await get_digest(subreddit, latest)
        if digest:
            return ToolResult(
                content=[TextContent(text=json.dumps(digest, indent=2))]
            )
        else:
            return ToolResult(
                error=ToolResultError(message="Digest not found")
            )
    
    @server.tool
    async def search_posts_tool(subreddit: str = None, query: str = "", limit: int = 10) -> ToolResult:
        posts = await search_posts(subreddit, query, limit)
        return ToolResult(
            content=[TextContent(text=json.dumps(posts, indent=2))]
        )
    
    @server.tool
    async def get_post_tool(post_id: str) -> ToolResult:
        post = await get_post(post_id)
        if post:
            return ToolResult(
                content=[TextContent(text=json.dumps(post, indent=2))]
            )
        else:
            return ToolResult(
                error=ToolResultError(message="Post not found")
            )
    
    transport = StdioTransport()
    await server.run(transport)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
