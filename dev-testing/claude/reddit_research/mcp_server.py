"""MCP stdio server. Tools per v1.spec §15."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from reddit_research.cache import Cache
from reddit_research.cli import (
    DEFAULT_CACHE_DB,
    DEFAULT_REPUTATION,
    run_ask,
)
from reddit_research.reputation import Reputation
from reddit_research.schema import Digest

server = Server("reddit-research")


@server.list_tools()
async def _list_tools() -> list[Tool]:
    return [
        Tool(
            name="ask",
            description=(
                "Run a prompt-driven Reddit research query. Returns the Digest as JSON."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "listing": {"type": "string", "enum": ["hot", "new", "top", "rising"]},
                    "time_filter": {"type": "string"},
                    "top": {"type": "integer"},
                    "comments": {"type": "integer"},
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="recall",
            description="Return a past Digest by prompt_hash, or the latest if no hash given.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt_hash": {"type": "string"},
                    "latest": {"type": "boolean"},
                },
            },
        ),
        Tool(
            name="list_prompts",
            description="Return recent prompt runs (prompt_text + ran_at + hash).",
            inputSchema={
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        ),
        Tool(
            name="search_posts",
            description="Substring search across titles and summary one_sentences in the cache.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "subreddit": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="reputation_for",
            description="Return the reputation entry for a topic area.",
            inputSchema={
                "type": "object",
                "properties": {"area": {"type": "string"}},
                "required": ["area"],
            },
        ),
    ]


@server.call_tool()
async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "ask":
        result = run_ask(
            arguments["prompt"],
            listing=arguments.get("listing", "top"),
            time_filter=arguments.get("time_filter", "month"),
            top_k=arguments.get("top", 15),
            comments_per_post=arguments.get("comments", 10),
            stream_digest=False,
        )
        return [TextContent(type="text", text=result["digest"].model_dump_json())]

    if name == "recall":
        cache = Cache(DEFAULT_CACHE_DB)
        try:
            if "prompt_hash" in arguments and arguments["prompt_hash"]:
                row = cache.get_prompt(arguments["prompt_hash"])
            else:
                rows = cache.list_prompts(limit=1)
                row = rows[0] if rows else None
            if row is None:
                return [TextContent(type="text", text='{"error":"not found"}')]
            return [TextContent(type="text", text=row.digest_json)]
        finally:
            cache.close()

    if name == "list_prompts":
        cache = Cache(DEFAULT_CACHE_DB)
        try:
            rows = cache.list_prompts(limit=arguments.get("limit", 20))
            payload = [
                {
                    "prompt_hash": r.prompt_hash,
                    "prompt_text": r.prompt_text,
                    "ran_at": r.ran_at,
                    "subreddits": r.subreddits,
                }
                for r in rows
            ]
            return [TextContent(type="text", text=json.dumps(payload))]
        finally:
            cache.close()

    if name == "search_posts":
        cache = Cache(DEFAULT_CACHE_DB)
        try:
            hits = cache.search_summaries(
                arguments["query"],
                subreddit=arguments.get("subreddit"),
                limit=arguments.get("limit", 10),
            )
            payload = [
                {"post_id": pid, "title": title, "sub": sub, "one_sentence": one}
                for pid, title, sub, one in hits
            ]
            return [TextContent(type="text", text=json.dumps(payload))]
        finally:
            cache.close()

    if name == "reputation_for":
        rep = Reputation(DEFAULT_REPUTATION)
        data = rep.load()
        entry = data.get("topic_areas", {}).get(arguments["area"], {})
        return [TextContent(type="text", text=json.dumps(entry))]

    return [TextContent(type="text", text=json.dumps({"error": f"unknown tool {name}"}))]


async def _amain() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
