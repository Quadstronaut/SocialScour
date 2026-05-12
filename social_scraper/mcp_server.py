"""MCP server exposing four tools: ask, discover, read_summary, read_timeline.

ask/discover return only {run_dir, summary_path, one_line_status} — no content.
read_summary/read_timeline are the explicit opt-in path for content.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


_DEFAULT_DATA_ROOT = Path("data")
_DEFAULT_CACHE = Path("cache/ollama_calls.sqlite")
_DEFAULT_REP = Path("cache/reputation.json")


def _impl_ask(
    topic: str,
    window_days: int = 30,
    sources: Optional[list[str]] = None,
    summarizer: str = "ollama",
    data_root: Optional[str] = None,
) -> dict[str, Any]:
    from social_scraper.core.llm.ollama import OllamaClient
    from social_scraper.core.pipeline.ask import AskConfig, run_ask
    from social_scraper.core.schema import SourceKind
    from social_scraper.core.sources.google_trends import GoogleTrendsClient
    from social_scraper.core.sources.hn import HNClient
    from social_scraper.core.sources.indiehackers import IndieHackersClient
    from social_scraper.core.sources.reddit import RedditClient, make_client

    root = Path(data_root) if data_root else _DEFAULT_DATA_ROOT
    src_list = [SourceKind(s) for s in sources] if sources else list(SourceKind)
    llm = OllamaClient(model="qwen3-coder:30b")
    if not llm.ping():
        return {"error": "ollama_unreachable", "run_dir": None, "summary_path": None}
    reddit = RedditClient(make_client())
    cfg = AskConfig(
        topic=topic, window_days=window_days, sources=src_list,
        summarizer=summarizer, data_root=root,
        cache_path=_DEFAULT_CACHE, reputation_path=_DEFAULT_REP,
    )
    result = run_ask(cfg, llm=llm, reddit=reddit, hn=HNClient(),
                     indiehackers=IndieHackersClient(), google_trends=GoogleTrendsClient())
    return {
        "run_dir": str(result["run_dir"]),
        "summary_path": str(result["summary_path"]),
        "one_line_status": result.get("narrative_preview", "ok")[:200],
    }


def _impl_discover(
    window_days: int = 30,
    top_n: int = 5,
    sources: Optional[list[str]] = None,
    data_root: Optional[str] = None,
) -> dict[str, Any]:
    from social_scraper.core.agent.discover import DiscoverConfig, run_discover
    from social_scraper.core.llm.ollama import OllamaClient
    from social_scraper.core.schema import SourceKind
    from social_scraper.core.sources.google_trends import GoogleTrendsClient
    from social_scraper.core.sources.hn import HNClient
    from social_scraper.core.sources.indiehackers import IndieHackersClient
    from social_scraper.core.sources.reddit import RedditClient, make_client

    root = Path(data_root) if data_root else _DEFAULT_DATA_ROOT
    src_list = [SourceKind(s) for s in sources] if sources else list(SourceKind)
    llm = OllamaClient(model="qwen3-coder:30b")
    if not llm.ping():
        return {"error": "ollama_unreachable", "run_dir": None, "summary_path": None}
    reddit = RedditClient(make_client())

    class _PickFirst:
        def pick_topics(self, candidates, top_n):
            return candidates[:top_n]

    cfg = DiscoverConfig(
        window_days=window_days, top_n=top_n, sources=src_list,
        data_root=root, cache_path=_DEFAULT_CACHE, reputation_path=_DEFAULT_REP,
    )
    result = run_discover(cfg, agent_driver=_PickFirst(), llm=llm, reddit=reddit,
                          hn=HNClient(), indiehackers=IndieHackersClient(),
                          google_trends=GoogleTrendsClient())
    return {
        "run_dir": str(result["run_dir"]),
        "summary_path": str(result["summary_path"]),
        "one_line_status": "discover_partial" if result.get("partial") else "ok",
    }


def _impl_read_summary(run_dir: str) -> dict[str, Any]:
    path = Path(run_dir) / "summary" / "summary.md"
    if not path.exists():
        return {"error": f"no summary at {path}"}
    return {"content": path.read_text(encoding="utf-8")}


def _impl_read_timeline(slug: str, data_root: Optional[str] = None) -> dict[str, Any]:
    root = Path(data_root) if data_root else _DEFAULT_DATA_ROOT
    path = root / "topics" / slug / "timeline.md"
    if not path.exists():
        return {"error": f"no timeline at {path}"}
    return {"content": path.read_text(encoding="utf-8")}


def main() -> None:
    """Entrypoint for the social-scraper-mcp script.

    Wires the four _impl_* functions into an MCP server via the `mcp` package.
    """
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("social-scraper")

    @server.tool()
    def ask(topic: str, window_days: int = 30,
            sources: Optional[list[str]] = None,
            summarizer: str = "ollama") -> dict:
        """Run the deterministic ask pipeline. Returns paths only."""
        return _impl_ask(topic, window_days, sources, summarizer)

    @server.tool()
    def discover(window_days: int = 30, top_n: int = 5,
                 sources: Optional[list[str]] = None) -> dict:
        """Run the agentic discover loop. Returns paths only."""
        return _impl_discover(window_days, top_n, sources)

    @server.tool()
    def read_summary(run_dir: str) -> dict:
        """Read the summary.md from a run folder."""
        return _impl_read_summary(run_dir)

    @server.tool()
    def read_timeline(slug: str) -> dict:
        """Read the timeline.md for a topic slug."""
        return _impl_read_timeline(slug)

    server.run()


if __name__ == "__main__":
    main()
