# SocialScour

Multi-source social aggregator. Given a topic, it pulls Reddit, Hacker News,
IndieHackers, and Google Trends into a single ranked Markdown digest. Designed
for decision-support: "is this a real problem people care about?"

Two entry points:

| Entry point | Driver | Command |
|---|---|---|
| `scour` CLI | Ollama (local, free) | `scour ask "your topic"` |
| `social-scraper-mcp` | Ollama (MCP tools) | see [MCP Setup](#mcp-setup) |

All data stays on-box. The output `.md` file is the artifact.

---

## Requirements

- Python ≥ 3.11
- [Ollama](https://ollama.com) running locally (`ollama serve`)
- Models pulled:
  ```
  ollama pull qwen3-coder:30b   # reasoning / summarization
  ollama pull bge-m3:latest     # embeddings (relevance ranking)
  ```
- `trendspy` or `pytrends` for Google Trends (installed automatically)

---

## Install

```bash
git clone https://github.com/Quadstronaut/SocialScour.git
cd SocialScour
pip install -e .
```

To confirm the install:

```bash
scour --help
```

---

## Quick Start

```bash
# Research a topic across all four sources (30-day window)
scour ask "local LLM coding assistants"

# Pin specific subreddits when you know the community (bypasses LLM discovery)
scour ask "Linux server hardening audit tools" \
  --subreddits sysadmin,selfhosted,linuxadmin,devops,cybersecurity \
  --window-days 90

# Narrow to specific sources
scour ask "open source billing tools" --sources reddit,hn --window-days 14

# --summarizer claude is accepted but has no effect; Ollama is always used
scour ask "container orchestration trends" --summarizer claude

# Discover what's trending without a topic
scour discover --top-n 5 --window-days 7

# Browse past runs
scour list
scour timeline <slug>
```

The interactive PowerShell launcher (`Scour-Sentiments.ps1`) wraps these
commands with menus if you prefer not to type flags.

---

## CLI Reference

### `scour ask <TOPIC>`

Fetch + rank + summarize posts about `TOPIC`. Writes `data/runs/<slug>_<timestamp>/summary/summary.md`.

| Flag | Default | Description |
|---|---|---|
| `--window-days N` | `30` | How far back to look (days) |
| `--sources LIST` | all | Comma-separated: `reddit,hn,indiehackers,trends` (alias `ih`, `google_trends`) |
| `--subreddits LIST` | (auto-discover) | Comma-separated subreddit names; bypasses LLM-driven discovery |
| `--model MODEL` | `qwen3-coder:30b` | Ollama model for summarization |
| `--summarizer NAME` | `ollama` | Accepted and stored in `meta.json`; has no effect on pipeline execution |
| `--out PATH` | `data` | Root folder for run output |

**Important:** Run `scour` from the repo root, or pass `--out` with an
absolute path. The defaults (`data/`, `cache/`) are relative to the working
directory.

### `scour discover`

Fetch trending titles from configured sources, pick the top-N, and run `ask`
on each.

| Flag | Default | Description |
|---|---|---|
| `--window-days N` | `30` | Lookback window |
| `--top-n N` | `5` | How many trending topics to dig into |
| `--sources LIST` | all | Same aliases as `ask` |
| `--model MODEL` | `qwen3-coder:30b` | Ollama model |
| `--out PATH` | `data` | Output root |

### `scour timeline <SLUG>`

Print the chronological digest history for a topic slug (stored in
`data/topics/<slug>/timeline.md`).

### `scour list`

List recent runs newest-first.

| Flag | Default | Description |
|---|---|---|
| `--data-root PATH` | `data` | Output root |
| `--limit N` | `20` | Max rows to show |

---

## MCP Setup

`social-scraper-mcp` exposes four tools to Claude Code (or any MCP host):

| Tool | Description |
|---|---|
| `ask` | Run the `ask` pipeline. Returns `{run_dir, summary_path, one_line_status}` — paths only, no content |
| `discover` | Run the `discover` loop. Returns same shape |
| `read_summary` | Read `summary.md` from a `run_dir` |
| `read_timeline` | Read the timeline for a topic slug |

`ask` and `discover` return only paths. Call `read_summary` or `read_timeline`
as the explicit opt-in to retrieve content.

Add to your Claude Code MCP config (`.claude/settings.json` or global):

```json
{
  "mcpServers": {
    "social-scraper": {
      "command": "social-scraper-mcp"
    }
  }
}
```

The MCP server requires Ollama to be running. If Ollama is unreachable,
`ask`/`discover` return `{"error": "ollama_unreachable", ...}`.

**Known limitation:** `_impl_ask` in the MCP server does not expose a
`subreddits` parameter. Until that is added, subreddit discovery uses the LLM
path. Use the `scour` CLI with `--subreddits` if you need to pin communities.

---

## Configuration

No config file. All settings are CLI flags or environment variables:

| Env var | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_TIMEOUT` | `1800` | Per-request timeout in seconds |
| `REDDIT_USER_AGENT` | (generic UA string) | Override the Reddit user-agent |

---

## Output Structure

Each run writes to `data/runs/<slug>_<timestamp>/`:

```
meta.json          — run parameters, per-source stats, warnings, topic-confidence
raw/               — raw fetched posts per source (.jsonl) + Google Trends blob (.json)
ranked.jsonl       — all posts with relevance scores and reasons (full audit trail)
summary/
  summary.md       — the final digest
```

Per-topic history: `data/topics/<slug>/timeline.md`

The LLM call cache lives at `cache/ollama_calls.sqlite` (30-day TTL, keyed by
post ID + model name + role).

---

## Sources

| Source | Mechanism | Notes |
|---|---|---|
| Reddit | Public JSON API (no auth, no PRAW) | Rate-limited (2 s + jitter). Returns 403 if user-agent is flagged. |
| Hacker News | Algolia search API | Free, no auth. Fetches stories and comments. |
| IndieHackers | HTML scraper (BeautifulSoup) | Fixed to the `ideas-and-validation` category. Brittle to HTML changes. |
| Google Trends | `trendspy` (primary) / `pytrends` (fallback) | Unofficial API; occasional 429s treated as best-effort. |

Reddit requires **no API credentials** — the client uses the public `.json`
endpoint. If Reddit starts returning 403s, try setting a descriptive
`REDDIT_USER_AGENT` value.

---

## Known Issues & Gaps

- **Relative path defaults** — `data/` and `cache/` resolve relative to CWD. Run from the repo root or use `--out` with an absolute path.
- **`--summarizer claude` has no effect** — the flag is accepted and stored in `meta.json` but nothing in the pipeline branches on it. Ollama is always used for all pipeline steps.
- **LLM-driven subreddit discovery** selects general communities for niche topics. Use `--subreddits` to pin communities when you know them.
- **`scour discover` uses a simple pick-first driver**, not the full `smolagents.CodeAgent` loop described in the design spec. Functional for most use cases.
- **MCP `ask` tool missing `subreddits` param** — pin subreddits via the CLI for now.
- No `--version`, `--dry-run`, `--explain`, or `scour doctor` subcommand yet.

---

## Development

```bash
pip install -e ".[dev]"

# Fast unit tests (no network, no Ollama)
pytest -m component

# Full workflow tests with fakes
pytest -m workflow

# All non-e2e tests
pytest

# Live e2e (requires running Ollama + real APIs)
pytest tests/e2e --e2e -v
```

---

## License

MIT. See source headers. Author: Kyle Green (Quadstronaut).

Wiki: [github.com/Quadstronaut/SocialScour/wiki](https://github.com/Quadstronaut/SocialScour/wiki)
