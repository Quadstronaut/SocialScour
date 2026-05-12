# Build Prompt: Reddit Scraper + Summarizer

Paste the block below verbatim into each agent (aider, cline, continue, goose, opencode, …) as a single message. Run each agent from inside its own subfolder of this repo so its work is isolated. The prompt is intentionally prescriptive — the goal is a fair, apples-to-apples comparison of how each agent executes the *same* spec.

---

Build a Reddit scraper + summarizer in the current directory. Python 3.11+. Keep it under ~600 LOC total. Stick to the spec; do not add features I did not ask for.

## Goals
1. Scrape posts + top-N comments from one or more subreddits using Reddit's anonymous public JSON endpoints. No auth, no PRAW, no Selenium, no Devvit.
2. Summarize each post and produce a subreddit-level digest using a local LLM via Ollama.
3. Emit TWO artifacts per run from the same data:
   - Structured JSON consumable by other LLMs.
   - A natural-English Markdown digest readable by a human in under 5 minutes.
4. Expose the scraped data as an MCP server (stdio) so Claude Desktop / other MCP clients can query it.

## Stack (use exactly these — do not substitute)
- `httpx[http2]>=0.27` for HTTP fetching.
- `pydantic>=2.7` for schemas.
- `tenacity>=8.3` for retry on transient HTTP errors.
- `openai>=1.40` SDK pointed at `http://localhost:11434/v1` (api_key="ollama") for summarization. Default model: `qwen3-coder:30b`. Configurable via `--summary-model`.
- `mcp` (official Python `mcp` package) for the MCP server. Stdio transport.
- `typer>=0.12` for the CLI.

## Endpoints (use exactly these — they work without auth)
- Listing: `https://www.reddit.com/r/{sub}/{listing}.json?t={time_filter}&limit={n}&after={cursor}` where listing ∈ {hot, new, top, rising} and time_filter ∈ {hour, day, week, month, year, all}. (`hot`/`new`/`rising` ignore `t`.)
- Post + comments: `https://www.reddit.com/r/{sub}/comments/{post_id}.json?limit={n}&depth=1`. Response is a 2-element array: `[post_listing, comments_listing]`. Parse `comments_listing.data.children` where `kind == "t1"`.

Pagination: read `data.after` from the listing response; pass back as `?after=` until you've collected `--limit` posts or `after` is null.

## HTTP rules (critical — Reddit will 403 you otherwise)
- User-Agent header MUST be a real-looking string: `f"reddit-scraper/0.1 (by /u/anonymous; +https://github.com/local)"`. Never `python-requests/*` or empty. Make it configurable via env `REDDIT_USER_AGENT` with that as the default.
- Always send `Accept: application/json`.
- Rate limit: hard cap at **30 requests/minute**. Use a token-bucket or simple `time.sleep` with min 2.0s + jitter (±0.5s) between requests.
- Retry policy (tenacity): 3 attempts, exponential backoff starting at 2s, on `httpx.HTTPStatusError` for status 429/500/502/503/504, and on `httpx.TransportError`. Do NOT retry 403 — that means we're blocked; abort the run with a clear message: "Reddit returned 403 — User-Agent likely flagged. Try a different UA or wait a few hours."
- If a response body starts with `<` (HTML interstitial instead of JSON), treat as 403.
- Use a single `httpx.Client` for the whole run with `http2=True`, `timeout=30.0`, `follow_redirects=True`.

## File layout
```
./
  pyproject.toml            # deps + entry points
  README.md                 # usage in <60 lines
  reddit_scraper/
    __init__.py
    cli.py                  # `reddit-scrape` Typer entry point
    fetch.py                # listing + comments fetchers; rate-limited HTTP client
    schema.py               # Pydantic models
    summarize.py            # post-level + digest-level Ollama calls
    render.py               # JSON + Markdown writers
    mcp_server.py           # `reddit-scrape-mcp` stdio entry point
  data/                     # gitignored runtime output
```

## Pydantic schemas (define exactly these fields)
- `RawComment`: id, author, body, score, created_utc, depth, parent_id
- `RawPost`: id, subreddit, title, author, url, permalink, selftext, score, upvote_ratio, num_comments, created_utc, flair, is_self, top_comments: list[RawComment]
- `PostSummary`: post_id, one_sentence (≤25 words), three_bullets (3 strings), key_quotes (up to 3 verbatim comment quotes), sentiment ("positive"|"neutral"|"negative"|"mixed"), topics (1–5 lowercase tags)
- `SubredditDigest`: subreddit, generated_utc, window (listing+time-filter), post_count, themes (list[str]), narrative (4–8 sentences), notable_posts (list of {post_id, why_notable})

JSON output shape: `{"meta": {...}, "posts": [{"raw": RawPost, "summary": PostSummary}, ...], "digest": SubredditDigest}`.

## Field mapping from JSON response
For listing entries, the post data lives at `child.data` where `child.kind == "t3"`. Map:
- id ← `data.id`
- subreddit ← `data.subreddit`
- title ← `data.title`
- author ← `data.author` (may be `[deleted]`)
- url ← `data.url`
- permalink ← `f"https://www.reddit.com{data.permalink}"`
- selftext ← `data.selftext` (empty string if missing)
- score ← `data.score`
- upvote_ratio ← `data.upvote_ratio`
- num_comments ← `data.num_comments`
- created_utc ← `data.created_utc`
- flair ← `data.link_flair_text` (may be null)
- is_self ← `data.is_self`

For comments (`child.kind == "t1"`):
- id ← `data.id`
- author ← `data.author`
- body ← `data.body`
- score ← `data.score`
- created_utc ← `data.created_utc`
- depth ← `data.depth` (0 for top-level)
- parent_id ← strip `t3_` prefix from `data.parent_id`

Take only top-level comments (`depth == 0`), sorted by score descending, take top `--comments` items. Skip `MoreComments` entries (`kind == "more"`).

## CLI
```
reddit-scrape run \
  --subreddit python --subreddit rust \
  --listing top --time-filter week \
  --limit 25 --comments 10 --min-score 50 \
  --out data/ --summary-model qwen3-coder:30b
```
Outputs per subreddit:
- `data/{sub}_{listing}_{UTC-ISO}.json`
- `data/{sub}_{listing}_{UTC-ISO}.md`

If multiple subs, also write `data/digest_{UTC-ISO}.{json,md}` covering all of them.

## Markdown shape
```
# r/{sub} — {listing}/{time-filter} — {date}

{digest.narrative}

**Themes:** {comma-separated themes}

## Notable posts
- **{title}** (score {score}, {num_comments} comments) — {why_notable}
  {one_sentence}
  - {bullet 1}
  - {bullet 2}
  - {bullet 3}
  > {key_quote_1}
  [link]({permalink})
```

## Summarization prompts (constants in `summarize.py`)
- Post-level system: "You summarize Reddit posts for downstream LLMs and humans. Be faithful, concrete, and quote real comments. Never invent facts. Output ONLY valid JSON matching the requested schema."
- Digest-level system: "You write a 4–8 sentence plain-English briefing on what is currently happening in a subreddit, based on the provided post summaries. Name specific themes, tensions, and notable threads. No hedging."

Use OpenAI SDK JSON mode (`response_format={"type": "json_object"}`) for post summaries. Plain text completion for the digest narrative.

## MCP server (`reddit-scrape-mcp`)
Stdio transport. Tools:
- `list_runs()` → available `data/*.json` with metadata.
- `get_digest(subreddit, latest=True)` → SubredditDigest for latest run.
- `search_posts(subreddit | None, query, limit=10)` → substring match across titles + summaries; returns PostSummary list.
- `get_post(post_id)` → full RawPost + PostSummary.

Read from JSON files on disk each call. No DB.

## Non-goals (do NOT do these)
- No web UI, no FastAPI, no Docker, no async producer/consumer, no SQLite, no embeddings, no scheduling, no auth flows.
- No nested-comment recursion (top-level only for v1).
- No tests beyond ONE smoke test that fetches r/test (limit=2, comments=2) and asserts the JSON validates.

## Acceptance check
```
reddit-scrape run --subreddit test --limit 3 --comments 3 --out data/
ls data/test_*.json data/test_*.md
python -c "from reddit_scraper.schema import *; import json, glob; d=json.load(open(sorted(glob.glob('data/test_*.json'))[-1])); print(len(d['posts']), d['digest']['narrative'][:80])"
```
Both files exist, JSON validates, narrative is non-empty. Done.

Build order: `pyproject.toml` → `schema.py` → `fetch.py` → `summarize.py` → `render.py` → `cli.py` → `mcp_server.py`. Show me each file as you go and wait for me to say "continue" between major steps.
