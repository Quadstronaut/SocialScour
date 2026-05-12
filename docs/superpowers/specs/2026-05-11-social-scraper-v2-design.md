# Social Scraper v2 — Design

**Date**: 2026-05-11
**Status**: Approved (operator sign-off in brainstorming session 2026-05-11)
**Supersedes**: `dev-testing/claude/` (kept as reference; code partially ported)

## 1. Goal

Quickly and accurately aggregate verified data points from Reddit and other social sources into a single per-topic summary, with a 30-day default analysis window. Runs are LLM-driven and execute either fully locally (Ollama) or via Claude Code, depending on entry point. All outputs stay on-box.

## 2. Non-Goals

- Cross-machine sync. All data and summaries are gitignored.
- Building a UI. CLI + MCP server only.
- Real-time / streaming aggregation. Each run is a discrete batch.
- Anything past v1 sources (Reddit, Google Trends, HN, IndieHackers). X/Twitter, YouTube, TikTok, generic trend aggregators are explicitly deferred.
- Single-user assumption. No auth, no multi-tenancy.

## 3. Operating Model

### 3.1 Two entry points, one shared library

Both entry points wrap the same `social_scraper.core` library. They never talk to each other.

| Entry point | Driver | Default use |
|---|---|---|
| `scrape` CLI | Local Ollama (default `qwen3-coder:30b`) | Day-to-day, fully offline-capable, no Anthropic billing. |
| `social-scraper-mcp` MCP server | Whatever Claude Code session launches it | When Claude's reasoning is wanted on a hard topic. Default route from a Claude Code session — token-efficient because tools return paths, not content. |

Claude Code may also shell out to the `scrape` CLI via Bash as a fallback. MCP is the default route from Claude Code because of token efficiency.

### 3.2 Two modes

- **`ask "<topic>"`** — deterministic pipeline. LLM is called at discrete steps (discover, rank, summarize, narrate). 95% of runs are this mode.
- **`discover`** — agentic loop using `smolagents`. LLM picks which trending topics to investigate. Used when the topic isn't known.

### 3.3 Summarizer override

In the MCP path, Claude Code can pass `summarizer="claude"` to do summarization with Claude rather than Ollama. Default is `"ollama"` for token efficiency. CLI exposes the same via `--summarizer=claude` (shells out to `claude -p`).

## 4. CLI Surface

```
scrape ask "<topic>" [--window-days 30] [--sources reddit,trends,hn,ih]
                     [--model qwen3-coder:30b] [--summarizer ollama|claude]
                     [--out ./data]
scrape discover      [--window-days 30] [--top-n 5] [--sources ...]
scrape timeline <topic-slug>
scrape list
```

Notes:
- `--sources` is comma-separated; default is all four.
- `--window-days` defaults to 30.
- `--summarizer=claude` shells out to `claude -p "<prompt>"`.

## 5. MCP Tool Surface

Four tools. All `ask` / `discover` tools return only `{run_dir, summary_path, one_line_status}` — never inline content. Claude opens content explicitly via the read tools.

| Tool | Args | Returns |
|---|---|---|
| `ask` | `topic: str, window_days: int = 30, sources: list[str] = ALL, summarizer: "ollama"\|"claude" = "ollama"` | `{run_dir, summary_path, one_line_status}` |
| `discover` | `window_days: int = 30, top_n: int = 5, sources: list[str] = ALL` | `{run_dir, summary_path, one_line_status}` |
| `read_summary` | `run_dir: str` | `{content: str}` — the summary.md text |
| `read_timeline` | `topic_slug: str` | `{content: str}` — the timeline.md text |

## 6. Package Layout

```
social_scraper/
├── __init__.py
├── cli.py                       # Typer CLI: ask, discover, timeline, list
├── mcp_server.py                # 4-tool MCP server
├── core/
│   ├── sources/
│   │   ├── reddit.py            # ported from dev-testing/claude
│   │   ├── google_trends.py     # TrendsPyG wrapper
│   │   ├── hn.py                # Algolia + Firebase
│   │   └── indiehackers.py      # BeautifulSoup
│   ├── llm/
│   │   ├── ollama.py            # /api/chat, format:json mode
│   │   └── claude.py            # subprocess to `claude -p`
│   ├── pipeline/
│   │   ├── ask.py               # discover → rank → fetch → summarize → narrate
│   │   ├── discover_subs.py     # source/sub discovery step
│   │   ├── rank.py              # strict-JSON LLM ranking + repair pass
│   │   ├── summarize.py
│   │   └── narrate.py
│   ├── agent/
│   │   └── discover.py          # smolagents CodeAgent loop, 5-iter cap
│   ├── store/
│   │   ├── run.py               # per-run folder writer
│   │   ├── timeline.py          # per-topic timeline appender
│   │   ├── cache.py             # 30-day SQLite LLM-call cache
│   │   └── reputation.py        # ported from dev-testing/claude — sub pinning per area
│   └── schema.py                # pydantic models: RawPost, RawComment, PostSummary, Digest, RunMeta
└── tests/
    ├── component/
    ├── workflow/
    └── e2e/
```

Project root stays `RedditScraper/` for git continuity. Operator will rename the parent folder later when no active sessions are running.

## 7. On-Disk Layout

```
RedditScraper/
├── data/                              # gitignored
│   ├── runs/
│   │   └── <slug>_<utc>/              # e.g. vibecoding_2026-05-11T14-22-03Z/
│   │       ├── meta.json              # RunMeta: topic, window, sources, model, summarizer, timing, warnings
│   │       ├── raw/
│   │       │   ├── reddit.jsonl
│   │       │   ├── google_trends.json
│   │       │   ├── hn.jsonl
│   │       │   └── indiehackers.jsonl
│   │       ├── ranked.jsonl
│   │       └── summary/
│   │           └── summary.md         # the readable artifact
│   └── topics/
│       └── <slug>/
│           └── timeline.md            # appended every run; H2 per run
└── cache/
    └── ollama_calls.sqlite            # 30-day TTL, keyed by (item_id, model, summarizer_role)
```

`.gitignore` additions: `data/`, `cache/`, `*.egg-info`, `__pycache__/`, `.pytest_cache/`.

Slug rule: lowercase, alphanumerics + `-`, max 60 chars, derived from topic. UTC stamp format: `YYYY-MM-DDTHH-MM-SSZ`.

## 8. Pipeline — `ask "<topic>"`

1. **Discover** — Ollama proposes relevant subreddits, HN keyword variants, and Google Trends related-query seeds. Reddit `about` calls + sub-search verify subs (>1000 subscribers, public). Caches result per-area.
2. **Fetch (shallow)** — All four sources in parallel via `asyncio.gather`. Reddit listings (top/month default), Trends interest-over-time + top queries, HN Algolia search, IH listing scrape. Per-source throttling: Reddit 2s (preserved from dev-testing/claude), IH 3s (preserved from ProductResearch), HN no throttle (Algolia free tier is generous), Trends 1s (TrendsPyG default).
3. **Rank** — Ollama in strict-JSON mode (`format: "json"` + pydantic schema in system prompt) scores each candidate item 0.0–1.0 for relevance to the topic. Pipeline orders by `(llm_score desc, native_score desc)`. Top-K per source kept (default K=15 for Reddit, 10 for HN, 5 for IH).
4. **Fetch (deep)** — pull top comments / replies for kept items.
5. **Summarize per item** — Ollama (or Claude if overridden) produces `PostSummary`. Result cached in `ollama_calls.sqlite` keyed by `(item_id, model, summarizer_role)`.
6. **Narrate** — Ollama writes the cross-source narrative (streamed to stdout AND `summary/summary.md`). Includes: themes, per-source sentiment, notable items with citations, verdict.
7. **Timeline append** — H2 block appended to `topics/<slug>/timeline.md`: UTC stamp + run-folder relative link + narrative's first paragraph.

## 9. Agentic Loop — `discover`

Uses `smolagents.CodeAgent`. Tools exposed to the LLM:

- `top_trending_reddit(window_days, limit) -> list[str]` — pulls /r/popular + /r/all top + per-area top items
- `top_trending_hn(window_days, limit) -> list[str]`
- `top_trending_google(window_days, limit) -> list[str]` — TrendsPyG trending searches
- `fetch_topic(topic, window_days) -> {run_dir, summary_path}` — internally calls `pipeline.ask`
- `summarize_across(run_dirs) -> str` — cross-topic meta-summary

Hard caps:
- Max 5 iterations.
- 90s wall-clock per iteration.
- If cap hit, write what was collected and exit with a `discover_partial` warning.

Output written to a parent `runs/discover_<utc>/` folder containing the per-topic child runs plus a top-level `summary/summary.md` (the meta-summary).

## 10. LLM Contract — Strict JSON Mode

Root cause of the dev-testing/claude G5 incident: `rank.py` parsed free-form text as JSON and failed schema validation.

Fix:
1. All LLM calls that expect structured output use Ollama's `/api/chat` with `format: "json"`.
2. Pydantic schema is rendered into the system prompt as an explicit `Return JSON conforming to: { ... }` block.
3. On parse failure, one repair retry: send the model its own malformed output with `"This must be valid JSON for schema X. Return ONLY the JSON, no commentary."`
4. On second failure, deterministic fallback per call site:
   - `rank` → order by native score + comment count.
   - `discover_subs` → use only reputation-pinned subs.
   - `summarize` → use first 800 chars of post + top comment as the "summary".
5. Every fallback writes a warning to `meta.json.warnings` so operator can see degradation.

## 11. Error Handling

| Failure | Behavior |
|---|---|
| Ollama not reachable | CLI exits with hint to run `ollama serve`. MCP returns `{error: "ollama_unreachable", paths: null}`. No partial run. |
| Per-source HTTP failures | tenacity retry (exp, 3 attempts). If a source fully fails, mark `blocked` in `meta.json`, continue with remaining sources, downgrade narrative confidence one notch. |
| LLM malformed JSON | See §10. |
| smolagents stall | 5-iter / 90s-per-iter cap. Partial write + `discover_partial` warning. |
| Empty results across all sources | Exit with "no data — try a different topic or wider window". No empty summary file. |
| Reddit 403 (UA blocked) | Reuse `RedditBlockedError` from dev-testing/claude. Surface UA, exit, no retry storm. |

## 12. Configuration & Secrets

- No required secrets for v1. Reddit free JSON, Google Trends unofficial, HN public APIs, IH scraped.
- Ollama base URL configurable via `OLLAMA_BASE_URL` env var, defaults to `http://localhost:11434`.
- `--summarizer=claude` requires `claude` CLI in PATH or `ANTHROPIC_API_KEY` if SDK path is taken (decision: prefer subprocess to avoid an SDK dependency in v1).
- Reddit User-Agent configurable via `REDDIT_USER_AGENT` env var.

## 13. Testing Strategy

Three layers. Operator's rule: **every layer must run 3 consecutive times with zero errors before any milestone is "done"**.

### 13.1 Component tests (`pytest -m component`)

- Each `sources/*` module against recorded HTTP fixtures (`vcrpy` or static JSON files in `tests/component/fixtures/`).
- `llm/ollama.py`: JSON-mode parsing, the malformed-JSON repair path, the deterministic fallback. Use a fake HTTP server.
- `llm/claude.py`: subprocess invocation mocked.
- `store/run.py`, `store/timeline.py`, `store/cache.py` against `tmp_path`.
- Each pipeline step (`discover_subs`, `rank`, `summarize`, `narrate`) with fake LLM + recorded HTTP.
- Each `agent` tool function in isolation.
- Bar: ≥30 unit tests, `pytest --count=3 -m component` green.

### 13.2 Workflow tests (`pytest -m workflow`)

- Full `ask` pipeline against fully recorded fixtures (no network, no Ollama).
- Full `discover` agentic loop with stubbed LLM driver that exercises real tool dispatch.
- MCP server tools: spin up in-process, call each, assert return shape is `{run_dir, summary_path, one_line_status}` only.
- Asserts: correct files written, timeline appended, meta.json populated, warnings empty on golden path.
- Bar: 8-12 tests, `pytest --count=3 -m workflow` green.

### 13.3 End-to-end tests (`pytest -m e2e --e2e`)

- Real Ollama with `qwen3-coder:30b`, real Reddit/HN/IH/Trends.
- One known-good topic ("local LLM coding") with `--window-days=7` for speed.
- Asserts: `summary.md` non-empty, ≥3 sources represented, timeline updated, `meta.json.warnings` empty.
- Bar: 3 consecutive clean runs. A 1/3 failure is treated as a real bug, not flake.

### 13.4 CI

- Component + workflow on every push.
- E2E manual, gated behind `--e2e` flag, run by operator before declaring v1 done.

## 14. Dependencies (v1)

Direct:
- `httpx[http2]` — Reddit, HN, generic HTTP
- `pydantic>=2.7` — schemas
- `tenacity>=8.3` — retry
- `typer>=0.12` — CLI
- `beautifulsoup4` — IndieHackers parsing
- `trendspyg` — Google Trends (PyTrends successor, since PyTrends is archived)
- `smolagents` — discover-mode agent loop
- `mcp>=1.0` — MCP server
- `vcrpy` (dev) — HTTP fixture recording
- `pytest>=8.0`, `pytest-repeat`, `pytest-mock` (dev)

No PRAW for v1 — Reddit free JSON is sufficient and already proven in dev-testing/claude.
No Selenium / Playwright for v1 — none of v1's sources require a headless browser.

## 15. Migration Plan from dev-testing/claude

Code to port largely as-is:
- `fetch.py` → `core/sources/reddit.py`
- `discover.py` → split: subreddit discovery into `core/pipeline/discover_subs.py`, classification logic kept
- `reputation.py` → `core/store/reputation.py` (kept; useful for sub pinning)
- `cache.py` → `core/store/cache.py` (generalize from prompt-keyed to call-keyed)
- `schema.py` → `core/schema.py` (expand for multi-source)
- `summarize.py` → `core/pipeline/summarize.py` + `narrate.py`
- `render.py` → `core/store/run.py`
- `prompts.py` → kept, expand for multi-source

Code to rewrite:
- `rank.py` → rewrite around strict-JSON contract (§10). Was the G5 trigger.
- `llm.py` → split into `core/llm/ollama.py` + `core/llm/claude.py`.
- `cli.py` → rewrite for new subcommand surface.
- `mcp_server.py` → rewrite for 4-tool surface from §5.

Code lifted from ProductResearch:
- `scrapers/hn/` → `core/sources/hn.py`
- `scrapers/indiehackers/` → `core/sources/indiehackers.py`

## 16. Out-of-Scope (v2+)

- X/Twitter, YouTube comments, TikTok hashtags.
- knowyourmeme / Exploding Topics / generic trend-aggregator sources.
- Multi-machine sync of `data/` or `cache/`.
- Web UI.
- Cross-topic clustering (the ProductResearch use case).
- Background/scheduled runs.

## 17. Open Questions

None at design sign-off (2026-05-11). Operator confirmed: data root `data/`, LLM-call cache approved, no missing sources/modes/outputs flagged.
