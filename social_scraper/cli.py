"""scrape CLI — Ollama-driven local entry point."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from social_scraper.core.schema import SourceKind


app = typer.Typer(help="Multi-source social aggregator (Ollama-driven).")


_DEFAULT_DATA_ROOT = Path("data")
_DEFAULT_CACHE = Path("cache/ollama_calls.sqlite")
_DEFAULT_REP = Path("cache/reputation.json")


def _parse_sources(spec: Optional[str]) -> list[SourceKind]:
    if not spec:
        return list(SourceKind)
    aliases = {"reddit": "reddit", "trends": "google_trends",
               "google_trends": "google_trends", "hn": "hn",
               "indiehackers": "indiehackers", "ih": "indiehackers"}
    out: list[SourceKind] = []
    for tok in spec.split(","):
        key = tok.strip().lower()
        if not key:
            continue
        canonical = aliases.get(key)
        if canonical is None:
            raise typer.BadParameter(f"unknown source: {tok}")
        out.append(SourceKind(canonical))
    return out


@app.command()
def ask(
    topic: str = typer.Argument(...),
    window_days: int = typer.Option(30, "--window-days"),
    sources: Optional[str] = typer.Option(None, "--sources",
                                          help="comma-separated: reddit,trends,hn,ih"),
    subreddits: Optional[str] = typer.Option(
        None, "--subreddits",
        help=("comma-separated, e.g. sysadmin,selfhosted,linuxadmin. "
              "Use this when you already know which communities discuss the topic "
              "— bypasses LLM-driven discovery."),
    ),
    model: str = typer.Option("qwen3-coder:30b", "--model"),
    summarizer: str = typer.Option("ollama", "--summarizer", help="ollama|claude"),
    data_root: Path = typer.Option(_DEFAULT_DATA_ROOT, "--out"),
) -> None:
    from social_scraper.core.llm.ollama import OllamaClient
    from social_scraper.core.pipeline.ask import AskConfig, run_ask
    from social_scraper.core.sources.google_trends import GoogleTrendsClient
    from social_scraper.core.sources.hn import HNClient
    from social_scraper.core.sources.indiehackers import IndieHackersClient
    from social_scraper.core.sources.reddit import RedditClient, make_client

    llm = OllamaClient(model=model)
    if not llm.ping():
        typer.echo("Ollama not reachable — start it with `ollama serve`.", err=True)
        raise typer.Exit(2)

    http = make_client()
    reddit = RedditClient(http)
    hn = HNClient()
    ih = IndieHackersClient()
    trends = GoogleTrendsClient()

    pinned_subs = None
    if subreddits:
        pinned_subs = [s.strip() for s in subreddits.split(",") if s.strip()]

    cfg = AskConfig(
        topic=topic,
        window_days=window_days,
        sources=_parse_sources(sources),
        subreddits=pinned_subs,
        model=model,
        summarizer=summarizer,
        data_root=data_root,
        cache_path=_DEFAULT_CACHE,
        reputation_path=_DEFAULT_REP,
    )
    result = run_ask(cfg, llm=llm, reddit=reddit, hn=hn,
                     indiehackers=ih, google_trends=trends)
    typer.echo(f"\nWrote {result['summary_path']}")
    if result.get("warnings"):
        typer.echo("Warnings:")
        for w in result["warnings"]:
            typer.echo(f"  - {w}")


@app.command()
def discover(
    window_days: int = typer.Option(30, "--window-days"),
    top_n: int = typer.Option(5, "--top-n"),
    sources: Optional[str] = typer.Option(None, "--sources"),
    model: str = typer.Option("qwen3-coder:30b", "--model"),
    data_root: Path = typer.Option(_DEFAULT_DATA_ROOT, "--out"),
) -> None:
    from social_scraper.core.agent.discover import DiscoverConfig, run_discover
    from social_scraper.core.llm.ollama import OllamaClient
    from social_scraper.core.sources.google_trends import GoogleTrendsClient
    from social_scraper.core.sources.hn import HNClient
    from social_scraper.core.sources.indiehackers import IndieHackersClient
    from social_scraper.core.sources.reddit import RedditClient, make_client

    llm = OllamaClient(model=model)
    if not llm.ping():
        typer.echo("Ollama not reachable — start it with `ollama serve`.", err=True)
        raise typer.Exit(2)
    reddit = RedditClient(make_client())
    hn = HNClient()
    ih = IndieHackersClient()
    trends = GoogleTrendsClient()

    class _OllamaPickDriver:
        def pick_topics(self, candidates, top_n):
            user = (
                "Given these trending titles, pick the top "
                f"{top_n} that look like real, painful, specific topics "
                "worth a deep dive. Return JSON.\n\n" + "\n".join(f"- {c}" for c in candidates)
            )
            from pydantic import BaseModel
            class _Picks(BaseModel):
                picks: list[str]
            try:
                result = llm.json_call("You select research topics.", user, _Picks)
                return [p for p in result.picks if p in candidates][:top_n] or candidates[:top_n]
            except Exception:
                return candidates[:top_n]

    cfg = DiscoverConfig(
        window_days=window_days, top_n=top_n,
        sources=_parse_sources(sources), model=model,
        data_root=data_root, cache_path=_DEFAULT_CACHE, reputation_path=_DEFAULT_REP,
    )
    result = run_discover(cfg, agent_driver=_OllamaPickDriver(),
                          llm=llm, reddit=reddit, hn=hn,
                          indiehackers=ih, google_trends=trends)
    typer.echo(f"\nWrote {result['summary_path']}")
    if result.get("partial"):
        typer.echo("Warning: discover_partial — caps were hit.")


@app.command()
def timeline(
    slug: str = typer.Argument(...),
    data_root: Path = typer.Option(_DEFAULT_DATA_ROOT, "--data-root"),
) -> None:
    path = data_root / "topics" / slug / "timeline.md"
    if not path.exists():
        typer.echo(f"no timeline for {slug} at {path}", err=True)
        raise typer.Exit(1)
    typer.echo(path.read_text())


@app.command(name="list")
def list_runs(
    data_root: Path = typer.Option(_DEFAULT_DATA_ROOT, "--data-root"),
    limit: int = typer.Option(20),
) -> None:
    runs_dir = data_root / "runs"
    if not runs_dir.exists():
        typer.echo("(no runs yet)")
        return
    items = sorted(runs_dir.iterdir(), key=lambda p: p.name, reverse=True)[:limit]
    for p in items:
        typer.echo(p.name)


if __name__ == "__main__":
    app()
