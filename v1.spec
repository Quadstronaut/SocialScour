# v1.spec — Claude Reddit Research

Prompt-driven Reddit research tool living at `./claude/`. **Different product** from
`build-prompt.md` (which is the bake-off "scrape r/python top week and digest" spec).
This one takes a natural-language prompt, finds relevant subreddits via LLM + Reddit
verification + a growing reputation file, harvests posts and substantive comments with
a two-pass relevance pipeline, summarizes, presents, and caches with a 30-day TTL.

Build target: ~1000–1200 LOC. Python 3.11+, Windows-first (PowerShell), Ollama for LLM.

---

## 1. Goals (in priority order)

1. Given a prompt, return a human-readable digest of what Reddit is saying about it,
   drawing only on substantive content (filtered comments, not memes).
2. Get smarter over time per topic area: subreddits that produce good signal for a
   topic get auto-promoted; ones that produce noise can be demoted.
3. Cheap re-visits: re-running the same prompt within 30 days hits cache, skipping
   both Reddit fetches and Ollama summarization.
4. Two consumer modes from one pipeline:
   - **Research mode** (default): terminal digest + `data/{slug}_{utc}.{md,json}` files.
   - **Ticker mode** (`--ticker NVDA --emit-sentiment <dir>`): appends one JSONL row
     per source subreddit to `<dir>/NVDA.jsonl` for TradingAgents consumption.
5. Expose the working memory over MCP stdio so Claude Desktop / other MCP clients
   can recall and search past runs.

## 2. Non-goals (v1)

- No web UI, no FastAPI, no Docker, no scheduler.
- No PRAW, no Reddit OAuth, no Selenium/Devvit.
- No nested-comment recursion (top-level only, same as `build-prompt.md`).
- No embeddings / vector search. Reputation file is the "memory" layer.
- No concurrent-writer story for `cache.db`. Single-process at a time.
- No auto-detection of tickers from prompt text — ticker mode requires explicit flag.
- No tests beyond a deterministic offline smoke test + one online end-to-end check.

## 3. Stack

Deliberately consistent with `build-prompt.md` so prompts/models stay swappable.

- Python 3.11+
- `httpx[http2]>=0.27` — HTTP client (single client per run, http2, follow_redirects)
- `pydantic>=2.7` — schemas (see §6)
- `tenacity>=8.3` — retry on transient HTTP errors
- `typer>=0.12` — CLI
- `openai>=1.40` SDK pointed at `http://localhost:11434/v1`, `api_key="ollama"`,
  default model `qwen3-coder:30b`, configurable via `--model`
- `mcp` (official Python `mcp` package) — stdio MCP server
- `sqlite3` (stdlib) — cache layer, raw SQL (no ORM)
- Std: `pytest` for tests

## 4. File layout

```
claude/
  pyproject.toml
  README.md
  v1.spec                  -> symlink/copy of repo-root v1.spec (optional)
  reddit_research/
    __init__.py
    cli.py                 -> `reddit-research` Typer entry point
    mcp_server.py          -> `reddit-research-mcp` stdio entry point
    fetch.py               -> rate-limited httpx client, listing/comments/about/search
    discover.py            -> LLM-proposes-subs + Reddit verification + reputation merge
    rank.py                -> pass-1 LLM relevance ranker (title+snippet only)
    filter.py              -> comment filter rules (score, length, etc.)
    summarize.py           -> per-post summary, per-sub sentiment, digest narrative
    reputation.py          -> auto-score + promote/demote, reads/writes reputation.json
    cache.py               -> SQLite layer: prompts, posts, summaries; 30-day purge
    render.py              -> markdown / json / jsonl writers
    schema.py              -> pydantic models
    prompts.py             -> all LLM prompt constants in one place
  data/                    -> gitignored: per-run .md and .json artifacts
  cache/
    cache.db               -> SQLite (gitignored)
    reputation.json        -> versioned manually; small, human-editable (gitignored)
  tests/
    test_smoke_offline.py  -> deterministic: mock httpx + Ollama, drive whole pipeline
    test_smoke_online.py   -> hits r/test, requires Ollama; run once, not in loop
    fixtures/
      listing_r_test.json
      comments_r_test.json
      subreddit_search.json
      subreddit_about.json
```

## 5. Pipeline (two-pass, Option B from brainstorming)

```
ask("how do people secure home networks")
  |
  v
[discover]                                             // §7
  llm_propose(prompt) -> ["homelab","netsec",
                          "HomeNetworking","crypto"]
  reddit_verify(...)  -> drop dead/private, get subscribers
  reputation_merge()  -> add top 3 reputed subs for this topic area
  =>                    final_subs: list[str]
  |
  v
[fetch listings]                                       // §8
  for sub in final_subs:
    /r/{sub}/{listing}.json?t={tf}&limit=N
    -> candidate_posts: list[RawPost] (no comments yet)
  cache hit on RawPost by post_id? reuse.
  |
  v
[rank: pass-1 LLM]                                     // §9
  feed prompt + [(title, selftext[:400], score, sub), ...] to LLM
  receive: ranked list of post_ids w/ relevance scores
  keep top K=15 (configurable --top)
  |
  v
[fetch comments]                                       // §8
  for post in top_K:
    /r/{sub}/comments/{id}.json?limit=N&depth=1
  cache hit on (post_id, comments fetched) within 24h? reuse.
  |
  v
[filter comments]                                      // §10
  drop depth>0, MoreComments, body too short, low score, bot patterns
  |
  v
[summarize per post]                                   // §11
  if summary cached for (post_id, model) -> reuse
  else -> Ollama JSON-mode call -> PostSummary
  |
  v
[per-sub aggregate + sentiment]                        // §11
  for sub in subs_actually_used:
    Ollama call -> {score: -1..+1, confidence: 0..1, theme: str}
  |
  v
[digest narrative]                                     // §11
  Ollama call on all PostSummaries -> 4-8 sentence narrative
  |
  v
[reputation auto-score]                                // §12
  for sub in subs_actually_used:
    if signal_density(sub) > threshold: +1 to topic area
    write cache/reputation.json
  |
  v
[render + emit]                                        // §13
  stream markdown digest to terminal
  write data/{slug}_{utc}.md
  write data/{slug}_{utc}.json
  if --ticker --emit-sentiment:
    append <emit-path>/{TICKER}.jsonl, one row per sub
  |
  v
[persist + purge]                                      // §14
  insert prompts row, posts rows, summaries rows
  DELETE WHERE fetched_at < now() - 30d
```

## 6. Pydantic schemas

```python
class RawComment(BaseModel):
    id: str
    author: str | None
    body: str
    score: int
    created_utc: float
    depth: int
    parent_id: str

class RawPost(BaseModel):
    id: str
    subreddit: str
    title: str
    author: str | None
    url: str
    permalink: str           # full https://www.reddit.com/...
    selftext: str
    score: int
    upvote_ratio: float
    num_comments: int
    created_utc: float
    flair: str | None
    is_self: bool
    top_comments: list[RawComment] = []

class PostSummary(BaseModel):
    post_id: str
    one_sentence: str        # <= 25 words
    three_bullets: list[str] # exactly 3
    key_quotes: list[str]    # 0..3 verbatim comment quotes
    sentiment: Literal["positive","neutral","negative","mixed"]
    topics: list[str]        # 1..5 lowercase tags
    relevance_to_prompt: float  # 0..1, from ranker

class SubSentiment(BaseModel):
    subreddit: str
    score: float             # -1..+1
    confidence: float        # 0..1
    n_posts: int
    n_comments: int
    theme: str               # 1 short sentence

class Digest(BaseModel):
    prompt: str
    generated_utc: str       # ISO Z
    subreddits_used: list[str]
    post_count: int
    themes: list[str]
    narrative: str           # 4..8 sentences
    notable_posts: list[dict]  # {post_id, why_notable}
    per_sub_sentiment: list[SubSentiment]
```

## 7. Subreddit discovery (`discover.py`)

**Step A — LLM proposes:**
Prompt the LLM (JSON mode) with the user prompt; ask for 5–15 likely subreddit names
*without* the `r/` prefix. System prompt forbids inventing names that "sound real";
LLM is told these will be verified and bogus names hurt.

**Step B — Reddit verifies:**
- For each proposed name: `GET /r/{name}/about.json`.
- Drop if 403/404/private/quarantined.
- Capture `subscribers`, `over18`, `subreddit_type`.
- Also call `/subreddits/search.json?q={prompt}&limit=10` and merge in any name
  with `subscribers > 1000` that wasn't already proposed.

**Step C — Reputation merge:**
- `cache/reputation.json` shape:
  ```json
  {
    "version": 1,
    "topic_areas": {
      "encryption": {
        "subs": {
          "crypto":  {"score": 7, "last_useful_utc": "2026-05-09T...", "promoted": false},
          "netsec":  {"score": 4, "last_useful_utc": "2026-04-22T...", "promoted": true}
        }
      },
      "home_networking": { "subs": {...} }
    }
  }
  ```
- Classify prompt to a topic area via LLM (single short call, returns existing area
  name or `"__new__"` + suggested slug).
- Take top-3 reputed subs for that area; union with steps A+B. De-dupe.
- Subs with `"promoted": true` are *always* included regardless of score (manual
  override via CLI; see §15).

**Final list:** capped at 8 subreddits per run (`--max-subs 8` default).

## 8. Fetching (`fetch.py`)

Identical HTTP rules to `build-prompt.md`:
- UA: `f"reddit-research/0.1 (by /u/anonymous; +https://github.com/local)"`,
  configurable via `REDDIT_USER_AGENT`.
- `Accept: application/json`.
- Single `httpx.Client(http2=True, timeout=30.0, follow_redirects=True)`.
- Rate cap: 30 req/min via token bucket. Min 2.0s + ±0.5s jitter between calls.
- Retry via `tenacity`: 3 attempts, exponential backoff from 2s, on 429/500/502/503/504
  and `httpx.TransportError`. Do NOT retry 403 — abort with the same message as the
  bake-off spec: *"Reddit returned 403 — User-Agent likely flagged. Try a different
  UA or wait a few hours."*
- If response body starts with `<` → treat as 403.

**Cache integration:** before each fetch, check `cache.db`:
- Listing fetches: not cached (cheap and we want fresh listings).
- Post+comments fetches: if `posts.post_id` row exists with `fetched_at` within 24h,
  reuse. Otherwise fetch and upsert.

## 9. Pass-1 ranker (`rank.py`)

Single Ollama call. JSON mode. Input:
- `prompt`: user's original question
- `candidates`: list of `{post_id, sub, title, selftext_snippet (first 400 chars), score, num_comments}`

System prompt: *"You are ranking Reddit posts by how directly they help answer the
user's question. Score 0..1. Strongly penalize meme/joke/circlejerk content. Return
ONLY valid JSON: `{"ranked":[{"post_id":"...","relevance":0.0}, ...]}`."*

Caller keeps top-K (default 15) by relevance, breaks ties by Reddit score.

## 10. Comment filter (`filter.py`)

Drop a comment if ANY of:
- `depth != 0` (top-level only)
- `kind == "more"` (MoreComments stub)
- `author in {"AutoModerator", "[deleted]"}` (configurable list in `prompts.py`)
- `score < 5` (configurable `--min-comment-score`)
- `len(body.strip()) < 120` chars — "not very very short" per user requirement
- body matches obvious bot patterns (regex list, e.g. starts with `^I am a bot`)

After filtering, keep top `--comments` (default 10) per post by score.

## 11. Summarization (`summarize.py`)

All Ollama calls go through one helper that:
- Uses OpenAI SDK pointed at `http://localhost:11434/v1`.
- For structured calls: `response_format={"type":"json_object"}`.
- Validates output via the matching pydantic model; on validation failure, one retry
  with `"Your previous output failed schema validation: {err}. Try again."` appended.

**Three call types:**

1. **PostSummary** — system prompt asks for one_sentence (≤25 words), exactly 3
   bullets, up to 3 verbatim comment quotes, sentiment label, 1–5 lowercase topic
   tags. Input: title + selftext + filtered top_comments.

2. **SubSentiment** — system: *"Score the overall sentiment of these Reddit posts
   regarding the user's prompt. Return ONLY JSON: `{"score": -1..1, "confidence": 0..1,
   "theme": "one short sentence"}`."* Input: prompt + the PostSummaries for that sub.

3. **Digest narrative** — plain text completion (not JSON). 4–8 sentences. System:
   *"You write a plain-English briefing on what Reddit communities are saying about
   the user's question. Name specific themes, tensions, and notable threads. No
   hedging."* Input: prompt + all PostSummaries + per-sub sentiments.

## 12. Reputation auto-scoring (`reputation.py`)

After the run completes successfully:
```
signal_density(sub) = (n_kept_comments / n_scraped_comments)
                    * mean_kept_comment_score
                    * mean_relevance_of_subs_posts_in_top_K
```
Bands:
- `signal_density > 0.6` → `reputation[area][sub].score += 1`, update `last_useful_utc`
- `0.3 <= signal_density <= 0.6` → no change
- `signal_density < 0.3` AND sub contributed ≥3 posts → `score -= 1`

Min score floor: `-3` (after that, sub is auto-excluded from future LLM proposals
for this area until manually re-promoted).

`promoted: true` subs are exempt from auto-decrement.

## 13. Cache schema (`cache.py`)

```sql
CREATE TABLE IF NOT EXISTS prompts (
  prompt_hash    TEXT PRIMARY KEY,    -- sha256 of normalized prompt+listing+tf
  prompt_text    TEXT NOT NULL,
  ran_at         TEXT NOT NULL,       -- ISO Z
  subreddits     TEXT NOT NULL,       -- JSON array
  post_ids       TEXT NOT NULL,       -- JSON array of selected top-K
  digest_md_path TEXT,                -- relative to claude/
  digest_json    TEXT                 -- full Digest JSON inline
);

CREATE TABLE IF NOT EXISTS posts (
  post_id     TEXT PRIMARY KEY,
  subreddit   TEXT NOT NULL,
  fetched_at  TEXT NOT NULL,          -- ISO Z
  raw_json    TEXT NOT NULL           -- full RawPost JSON
);

CREATE TABLE IF NOT EXISTS summaries (
  post_id        TEXT NOT NULL,
  model          TEXT NOT NULL,
  summarized_at  TEXT NOT NULL,
  summary_json   TEXT NOT NULL,       -- full PostSummary JSON
  PRIMARY KEY (post_id, model)
);

CREATE INDEX IF NOT EXISTS idx_posts_fetched_at ON posts(fetched_at);
CREATE INDEX IF NOT EXISTS idx_prompts_ran_at   ON prompts(ran_at);
```

Normalized prompt for hashing: lowercase, collapse whitespace, strip punctuation
except `?`. NOT semantic — same words in same order = cache hit.

**30-day purge:** at start of every run, `DELETE FROM posts WHERE fetched_at <
datetime('now','-30 days')`. Same for `prompts` and `summaries`.

## 14. CLI (`reddit-research`)

```
reddit-research ask <prompt> [options]
  --listing {hot|new|top|rising}     default: top
  --time-filter {hour|day|week|month|year|all}  default: month
  --limit N             per-sub listing limit          default: 25
  --top K               keep K posts after ranking      default: 15
  --comments N          comments per post                default: 10
  --min-comment-score N                                  default: 5
  --max-subs N          cap on final subreddit list     default: 8
  --model MODEL                                          default: qwen3-coder:30b
  --out DIR             where .md/.json land            default: claude/data
  --ticker SYMBOL       enables TradingAgents output
  --emit-sentiment DIR  required if --ticker; per-ticker JSONL goes here
  --no-cache            force fresh fetches + summaries
  --offline             use cached data only; fail if any required item missing

reddit-research promote <sub> <area>   -> set promoted:true for sub in area
reddit-research demote  <sub> <area>   -> set promoted:false; reset score to 0
reddit-research recall  [--latest|--prompt-hash H]  -> reprint a past digest
reddit-research list-prompts [--limit 20]
reddit-research purge                 -> manual 30-day purge
reddit-research stats                 -> rows in each table, db size, top reputed subs
```

## 15. MCP server (`reddit-research-mcp`, stdio)

Tools (all read-only against `cache.db` and `reputation.json` — no fetches):
- `ask(prompt, listing?, time_filter?, top?, comments?)` → runs full pipeline,
  returns Digest JSON. (This is the one tool that's not read-only.)
- `recall(prompt_hash? | latest=True)` → Digest JSON
- `list_prompts(limit=20)` → recent runs with prompt_text + ran_at
- `search_posts(query, subreddit?, limit=10)` → substring match across titles +
  summaries; returns list of `{post_id, title, sub, one_sentence}`
- `get_post(post_id)` → `{raw: RawPost, summary: PostSummary}`
- `reputation_for(area)` → contents of `reputation.json[topic_areas][area]`

## 16. Output artifacts

**Terminal:** stream markdown digest line-by-line as Ollama writes the narrative
(use the OpenAI SDK streaming mode for the digest call only — post summaries are
non-streaming JSON-mode).

**`data/{slug}_{utc}.md`** — same shape as `build-prompt.md`:
```
# {prompt} — {date UTC}

{digest.narrative}

**Themes:** {comma-separated themes}
**Subreddits used:** {comma-separated subs}

## Notable posts
- **{title}** (r/{sub}, score {score}, {num_comments} comments) — {why_notable}
  {one_sentence}
  - {bullet 1}
  - {bullet 2}
  - {bullet 3}
  > {key_quote_1}
  [link]({permalink})

## Per-subreddit sentiment
| Subreddit | Score | Confidence | n posts | n comments | Theme |
|-----------|-------|------------|---------|------------|-------|
| ...
```

**`data/{slug}_{utc}.json`:** full Digest object plus the embedded list of
`{raw: RawPost, summary: PostSummary}` for the top-K posts.

**JSONL for TradingAgents** (only when `--ticker` and `--emit-sentiment` are set):
one row per source subreddit appended to `<dir>/{TICKER}.jsonl`:
```json
{"ts":"2026-05-11T13:55:00Z","ticker":"NVDA","sub":"wallstreetbets",
 "score":0.74,"confidence":0.81,"n_posts":42,"n_comments":318,
 "theme":"AI demand still strong","prompt":"NVDA outlook after earnings",
 "learning_version":"v1","model":"qwen3-coder:30b"}
```

`slug` is the prompt lowercased, non-alphanumerics → `-`, trimmed to 60 chars.

## 17. Error handling

- **Reddit 403:** abort run, write nothing to cache, exit code 2.
- **Reddit 429/5xx after retries:** abort run, exit code 3, partial cache writes are
  fine (they're atomic per post).
- **Ollama unreachable:** abort run before any fetching, exit code 4 with message
  *"Ollama not reachable at http://localhost:11434 — start it with `ollama serve`."*
- **Pydantic validation fail on LLM output:** one retry with error appended. If still
  fails, log the bad output to `cache/errors/{utc}.txt` and skip that summary (post
  still appears in digest, marked as `summary_failed`).
- **Cache.db locked:** retry 3× with 200ms backoff, then abort with clear message.

## 18. Testing strategy

**`tests/test_smoke_offline.py` — the loop target.**
- Mocks `httpx.Client` with canned fixture responses (listing, comments, about,
  search).
- Mocks Ollama with a `FakeOpenAI` that returns deterministic JSON.
- Drives full pipeline end-to-end through `cli.py`'s `ask` function (not subprocess).
- Asserts:
  1. Pipeline completes without exception.
  2. `data/*.md` and `data/*.json` files written.
  3. `cache.db` has 1 prompt row, ≥1 posts rows, ≥1 summaries rows.
  4. JSON validates against `Digest` schema.
  5. With `--ticker NVDA --emit-sentiment <tmpdir>`, exactly one
     `<tmpdir>/NVDA.jsonl` exists with N rows = N subs used, each row validates as
     `SubSentiment` + ticker fields.
  6. Second invocation of same prompt → 0 httpx calls (full cache hit).
  7. Reputation auto-score updates `reputation.json` when fixture is configured to
     produce high signal density.

**`tests/test_smoke_online.py` — sanity, run once at the very end.**
- Actually calls Reddit (`r/test`, `--limit 2 --comments 2`) and Ollama.
- Asserts files exist and JSON validates. Does NOT assert content.

**The loop:** run `pytest tests/test_smoke_offline.py -q` three times in a row.
Reset counter on any failure. Stop at 3 consecutive passes.

## 19. Acceptance check

```
pytest claude/tests/test_smoke_offline.py -q  # x3 in a row, no failures
pytest claude/tests/test_smoke_online.py -q   # x1, requires Ollama + network
reddit-research ask "test how this thing works" --limit 3 --comments 3
# -> prints markdown digest, exits 0, creates data/*.md + data/*.json
reddit-research recall --latest
# -> reprints the same digest from cache, no Ollama or Reddit calls
```

## 20. Build order

Each step ends with the offline smoke test passing for what's built so far:

1. `pyproject.toml`, package skeleton, `schema.py`
2. `cache.py` + its own tests (in-memory sqlite)
3. `fetch.py` with rate limiter + a fixture-driven test
4. `discover.py` (LLM-proposes step stubbed; Reddit-verify covered)
5. `rank.py` + `filter.py`
6. `summarize.py` (Ollama call wrapper + retry-on-validation-fail)
7. `reputation.py`
8. `render.py` (markdown + JSON + JSONL)
9. `cli.py` — wires it all together
10. `mcp_server.py`
11. Online smoke test
