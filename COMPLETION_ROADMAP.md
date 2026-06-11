# SocialScour — Completion Roadmap

**Generated:** 2026-05-15  
**Overall completion: 72%**

---

## 1. What SocialScour Is

A local, personal research tool. Given a topic, it aggregates Reddit, HN, IndieHackers, and Google Trends into a single ranked summary (`.md` file). Two entry points: `scour` CLI (Ollama-driven, fully offline) and `social-scraper-mcp` (4-tool MCP server for Claude Code). Two modes: deterministic `ask "<topic>"` (95% of runs) and agentic `discover` (trends surfacing). All data stays on-box. Designed for decision-support: "should I build this?" The output `.md` IS the artifact.

---

## 2. Overall Completion — 72%

| Component | % | Notes |
|-----------|---|-------|
| Schema (`core/schema.py`) | 100% | All v2 models implemented: `RawPost`, `RawComment`, `PostSummary`, `Digest`, `RunMeta`, `SourceStats`, `TopicConfidence` |
| LLM clients (`core/llm/`) | 95% | `ollama.py` complete: JSON mode, repair pass, embed, stream. `claude.py` basic subprocess only — no full pipeline integration |
| Store layer (`core/store/`) | 100% | `run.py`, `timeline.py`, `cache.py`, `reputation.py` all complete and tested |
| Reddit source (`core/sources/reddit.py`) | 100% | Rate-limited, `RedditBlockedError`, tenacity retry, comment fetch — all implemented |
| HN source (`core/sources/hn.py`) | 85% | Algolia search works. No fixture for zero-result warning; HN silently returns empty |
| IndieHackers source (`core/sources/indiehackers.py`) | 70% | Scraper works but keyed to `ideas-and-validation` category only; no keyword search; likely brittle to HTML changes |
| Google Trends source (`core/sources/google_trends.py`) | 75% | `interest_over_time` + `related_queries` work. `trendspy.Trends(request_delay=2.0)` not applied by default; 429 handling is warn-and-continue only |
| Pipeline — `discover_subs` | 75% | LLM propose + verify + merge works. **Discovery prompt is the root cause of the sysadmin bug** — it selects general subs over niche ones. No niche-preference weighting in the prompt |
| Pipeline — `rank` | 90% | Embeddings cosine sim with `bge-m3`, fallback on `OllamaError`. `drop_threshold=0.45` in `AskConfig` but `RankingResult` default is `0.55` — inconsistency. Threshold tuning unvalidated on the fixed e2e run |
| Pipeline — `summarize` | 95% | `PostSummary` JSON mode + OllamaError fallback. Functional |
| Pipeline — `narrate` | 90% | Streaming to stdout + capture. Starts with `# Digest` hardcoded, not the topic title |
| Pipeline — `ask` (orchestrator) | 85% | `--subreddits` bypass done. Per-source stats done. Topic-mismatch gate done. Topic-confidence check done. **Not validated against the e2e bug** — threshold tuned to 0.45 but original bug produced synthetic scores so we can't confirm this actually fires correctly yet |
| Agent — `discover` | 70% | `run_discover` loop with `_PickFirst` / `_OllamaPickDriver` — functional but `smolagents.CodeAgent` never actually used; the real agentic loop from spec §9 is a hand-rolled for-loop, not smolagents tool dispatch |
| CLI (`cli.py`) | 90% | `ask`, `discover`, `timeline`, `list`. All relative-path defaults (known bug in `execution-observations.md`). Missing: `--version`, `--dry-run`, `--explain`, `scour doctor` |
| MCP server (`mcp_server.py`) | 85% | Four tools present and correct return shape. `_impl_ask` missing `subreddits` passthrough. MCP path uses `_PickFirst` not `_OllamaPickDriver` for discover |
| Component tests | 95% | 39 tests covering every module. All pass 63/63 (including workflow). Missing: IH zero-result path, Trends request_delay, discover_subs prompt quality coverage |
| Workflow tests | 90% | `ask`, `discover`, `cli`, `mcp_server` covered with fake dependencies. Missing: `mcp_server ask/discover` live calls (only read_summary/read_timeline tested) |
| E2E tests | 60% | One test exists (`test_known_good_topic`). Runs with real Ollama + APIs. Never validated 3x-consecutive clean as spec requires. The 2026-05-14 run that failed used a different topic than the e2e test topic |
| PowerShell launcher (`Scour-Sentiments.ps1`) | 95% | Menu-driven wrapper with preflight. Functional. CWD bug workaround (it cd's to repo root) already applied |
| Docs | 60% | Design doc and plan doc complete. No README "Quick start". No `CHANGELOG`. No inline help examples |

---

## 3. Definition of "100% Done and Tested"

Per spec §13 — each layer must pass 3 consecutive runs with zero errors:

1. `pytest --count=3 -m component` green (≥30 unit tests — currently 39; bar met)
2. `pytest --count=3 -m workflow` green (8-12 tests — currently 9; bar met)
3. `pytest --e2e --count=3` green against real Ollama `qwen3-coder:30b` + real APIs
4. Manual: `scour ask "Linux server hardening audit tools" --window-days 90 --subreddits sysadmin,selfhosted,linuxadmin,devops,cybersecurity` produces a summary that mentions Lynis, OpenSCAP, or similar named tools
5. `meta.json` per-source stats present, `summary.md` has `topic-confidence:` header, run completes in under 15 minutes

---

## 4. Gap Analysis — v2 Design vs Current Code

### Gap 1: Discovery prompt quality (spec §8.1 — **blocker for dogfooding**)

Design says: "Ollama proposes relevant subreddits." Current code (`core/pipeline/discover_subs.py:28`, `DISCOVER_SYSTEM` prompt) says nothing about preferring niche subs over general ones. The `r/linux` incident proves this. The `--subreddits` bypass (`AskConfig.subreddits`) is implemented and tested but is a workaround, not a fix. The actual DISCOVER_SYSTEM prompt in `core/pipeline/prompts.py` needs to instruct the LLM to prefer specific/niche communities over flagship subreddits, and to use the full topic phrase to weight its choices.

### Gap 2: drop_threshold inconsistency (spec §10 — **bug**)

`AskConfig.drop_threshold = 0.45` but `RankingResult.drop_threshold = 0.55`. The `AskConfig` value wins at runtime because `rank_posts()` takes `drop_threshold` as a parameter from `ask.py:239`. The `RankingResult` default is a dead default that misleads anyone reading the class. The `0.45` value was updated from the TODO notes but has never been validated against a known-good e2e run.

### Gap 3: smolagents not actually used (spec §9 — **design gap**)

Spec §9 calls for `smolagents.CodeAgent` with tools exposed as `top_trending_reddit`, `top_trending_hn`, `fetch_topic`, `summarize_across`. What's in `core/agent/discover.py` is a hand-rolled for-loop with a `pick_topics` duck-typed driver. It satisfies the functional contract but bypasses the actual agentic loop. For personal use this may be fine, but the design intent is unmet. The `cli.py` discover command uses an inline `_OllamaPickDriver` that does basic LLM selection, not smolagents.

### Gap 4: MCP `ask` missing `subreddits` arg (spec §5 — **incomplete**)

`_impl_ask` in `mcp_server.py:17` takes `topic, window_days, sources, summarizer` but no `subreddits`. The spec §5 table doesn't list it either, but given the subreddit discovery bug is the #1 blocker, the MCP tool needs this parameter to be usable for decision-support queries.

### Gap 5: Trends 429 handling (spec §11 — **annoyance → bug**)

`trendspy` docs suggest `request_delay=2.0`. `_DefaultBackend.__init__` creates `Trends()` with no delay. A 429 logs to stdout but the spec says "downgrade narrative confidence one notch" and record to `meta.json`. Current code does `writer.mark_blocked()` but the narrative doesn't acknowledge missing Trends data.

### Gap 6: HN and IH silent empty (spec §11 — **annoyance**)

Per `execution-observations.md`: HN and IH produced zero data with no warning in the 2026-05-14 run. `ask.py` only calls `writer.mark_blocked()` on exception, but if `hn.search()` returns `[]` with no exception, there's no warning. Same for IH.

### Gap 7: Relative path defaults (spec §12 — **annoyance → bug**)

`cli.py:17-18` uses `Path("data")`, `Path("cache/ollama_calls.sqlite")`, `Path("cache/reputation.json")`. Running `scour` from any directory other than the repo root silently creates data in the wrong place. Spec says nothing about this but it's a known bug from `execution-observations.md`. Fix: resolve against a user-level config dir or fail with a clear message.

### Gap 8: No README, no `--version`, no `scour doctor` (spec §12 — **polish**)

CLI declares `scour` as entrypoint but `pyproject.toml` description mixes `scrape` and `social-scraper`. `execution-observations.md` notes the confusion. These are deferred per `TODO-tomorrow.md` but are needed before "done."

### Gap 9: Claude client not integrated into pipeline (spec §3.3 — **incomplete**)

`core/llm/claude.py` exists with `ClaudeClient.summarize()`. But `pipeline/summarize.py` only calls `llm.json_call()` — it always uses the Ollama path. `--summarizer=claude` in `AskConfig` is stored and passed through but `run_ask` never branches on it. The `claude` path is dead code.

### Gap 10: `_impl_ask`/`_impl_discover` have no timeout, no async (spec §9 — **incomplete**)

The MCP spec returns only `{run_dir, summary_path, one_line_status}`. The implementations call `run_ask` synchronously — fine for now but will block the MCP server for 10-18 minutes per call. Acceptable for personal use but should be documented.

---

## 5. Phased Path to 100%

### Phase 1 — Correctness (target: 78%)
**Goal:** produce trustworthy results on the known-failing query

Deliverables:
- [ ] `core/pipeline/prompts.py`: rewrite `DISCOVER_SYSTEM` to explicitly prefer niche, topic-specific subreddits over flagship/general communities. Add instruction: "For niche/professional topics, strongly prefer subreddits under 500k subscribers focused on the exact domain."
- [ ] `AskConfig.drop_threshold`: change from `0.45` to `0.55` to match `RankingResult` default, or document the divergence explicitly. Run the failing query and tune empirically.
- [ ] Warn when HN/IH return zero posts (in `ask.py`, after each source fetch if `len(posts) == 0`): `writer.add_warning(f"hn_zero_results:{cfg.topic}")`
- [ ] `trendspy`: apply `request_delay=2.0` in `_DefaultBackend.__init__` or via env var.
- [ ] Validate fix: `scour ask "Linux server hardening audit tools" --window-days 90 --subreddits sysadmin,selfhosted,linuxadmin,devops,cybersecurity` must mention Lynis/OpenSCAP.

Tests to add:
- `test_pipeline_discover_subs.py`: test that `propose_subreddits` prompt includes a niche-preference instruction (string check)
- `test_ask_zero_results_adds_warning`: fake HN/IH returning `[]`, assert `hn_zero_results` in `meta.json.warnings`

Verification: `pytest --count=3 -m component -m workflow` green

### Phase 2 — Feature completeness (target: 88%)
**Goal:** all spec features are implemented and exercised

Deliverables:
- [ ] `mcp_server.py:_impl_ask`: add `subreddits: Optional[list[str]] = None` parameter, plumb to `AskConfig`
- [ ] `pipeline/summarize.py`: implement `--summarizer=claude` branch — call `ClaudeClient.summarize()` when `summarizer == "claude"`; fall back to Ollama on `ClaudeError`
- [ ] `cli.py`: add `--version` (use `importlib.metadata.version("social-scraper")`)
- [ ] `cli.py`: add `scour doctor` subcommand — check Ollama reachable, model pulled, package importable, `bge-m3:latest` available, network reachable
- [ ] Absolute path resolution for `--out`, cache, reputation defaults

Tests to add:
- `test_mcp_server.py`: `test_impl_ask_accepts_subreddits_kwarg` — assert the kwarg exists and plumbs to AskConfig
- `test_cli.py`: `test_cli_version` — assert `scour --version` exits 0 and prints a version string
- `test_pipeline_summarize.py`: `test_summarize_uses_claude_when_specified` — mock `ClaudeClient`, assert it's called when `summarizer="claude"`

Verification: `pytest --count=3` (all non-e2e) green

### Phase 3 — E2E validation (target: 95%)
**Goal:** spec §13.3 e2e bar met

Deliverables:
- [ ] Run `pytest tests/e2e --e2e -v` — topic "local LLM coding", `--window-days 7`
- [ ] Fix any failures (likely: `bge-m3` embedding model must be pulled, Trends 429 may still fire)
- [ ] Run 3 consecutive times with zero failures
- [ ] Run the decision-support query for real: `scour ask "Linux server hardening audit tools" --window-days 90 --subreddits sysadmin,selfhosted,linuxadmin,devops,cybersecurity`
- [ ] Verify acceptance criteria from `TODO-tomorrow.md`: Lynis/OpenSCAP in summary, per-source stats in meta.json, topic-confidence header, <15 min runtime

### Phase 4 — Polish and docs (target: 100%)
**Goal:** tool is usable by anyone who can read a README

Deliverables:
- [ ] `README.md` with Quick Start block (4 canonical commands as in `execution-observations.md`)
- [ ] Fix script name consistency: `pyproject.toml` entrypoint is `scour`; update description and any `scrape` references in docs
- [ ] `--dry-run` flag on `ask`: fetch + rank + dump ranked candidates, ask Y/N before LLM summarization
- [ ] `--explain` flag: per-stage trace to stdout
- [ ] Ranker rationale persistence: `reason` field already written to `ranked.jsonl` — this is done
- [ ] `scour discover` uses `_OllamaPickDriver` which calls LLM. This is acceptable; document in README that full smolagents loop is v2+

---

## 6. Testing Strategy

### Unit-testable (no network, no Ollama)
- All schema validation (`test_schema.py`) — done
- `slugify`, `RunWriter`, `TimelineWriter`, `LLMCache`, `Reputation` — done
- `rank_posts` with `_FixedEmbedder` — done (6 tests including fallback path)
- `OllamaClient.json_call` + repair pass with `httpx.MockTransport` — done
- `ClaudeClient.summarize` with `subprocess` mock — done
- `discover_subs.propose_subreddits`, `verify_subreddits`, `merge_search` — partially done; missing prompt-content assertion

### Workflow-testable (all fakes, no network)
- Full `ask` pipeline (golden path, topic_mismatch, topic_confidence, pinned_subs, r/-prefix regression) — done (5 tests)
- Full `discover` loop — done (1 test)
- CLI subcommands — done (4 tests)
- MCP `read_summary`, `read_timeline` — done (3 tests); missing: `ask`/`discover` implementation tests (blocked by Ollama dependency in current impl)

### Integration-testable (recorded fixtures, no live network)
- `test_sources_reddit.py` uses `httpx.MockTransport` + JSON fixtures — done (4 tests)
- `test_sources_hn.py` uses recorded fixture — done (1 test)
- `test_sources_indiehackers.py` uses recorded HTML fixture — done (1 test)
- `test_sources_google_trends.py` uses a fake backend — done (1 test)
- **Gap**: no `vcrpy` cassettes yet — all HTTP fixtures are hand-crafted JSON/HTML, not real recorded responses

### E2E (live Ollama + live APIs)
- `test_real_ask.py::test_known_good_topic` — exists, never 3x-consecutive clean
- The failing query (`Linux server hardening audit tools`) is not a test — it's a manual acceptance criterion from `TODO-tomorrow.md`

### What needs a live Reddit API
- `test_real_ask.py` (gated behind `--e2e`)
- The `scour discover` command in practice (fetches `/r/popular`)
- Subreddit discovery in the `ask` pipeline (unless `--subreddits` is used)

### Snapshot-testable
- `summary.md` output format — not yet. A snapshot test would record a golden `summary.md` from a fully-fake run and diff future outputs. Low priority for personal use but useful if the narrative format changes.

---

## 7. Honest Blockers

| Blocker | What's needed |
|---------|---------------|
| `bge-m3:latest` must be pulled | `ollama pull bge-m3:latest` — user noted it's already pulled (1.2 GB, 6 days ago) |
| `qwen3-coder:30b` must be pulled | Already in use per 2026-05-14 run |
| `OLLAMA_BASE_URL` | Defaults to `http://localhost:11434` — no change needed unless Ollama is remote |
| Google Trends 429 | Unofficial API; `request_delay=2.0` reduces it but doesn't eliminate it. Treat Trends as "best-effort" for now |
| `--summarizer=claude` | Requires `claude` CLI in PATH (Claude Code CLI). No ANTHROPIC_API_KEY needed if using subprocess path |
| IH scraper fragility | IndieHackers HTML structure can change; `feed-item` CSS selector is brittle. No alternative |
| E2E tests must be run manually | `pytest tests/e2e --e2e` — cannot automate without live Ollama |
| smolagents not actually wired | If agentic `discover` with real LLM reasoning is wanted, the `smolagents.CodeAgent` loop must be implemented. Current code is a simpler stub. Decision needed: accept the stub or implement the full loop |
| Relative path defaults | User must run `scour` from the repo root or set `--out` explicitly. No fix is in Phase 1. |

---

## 8. Component-by-Component Status Summary

| File | Status | Missing |
|------|--------|---------|
| `social_scraper/__init__.py` | 100% | — |
| `social_scraper/cli.py` | 90% | `--version`, `doctor`, `--dry-run`, `--explain`, absolute path defaults |
| `social_scraper/mcp_server.py` | 85% | `subreddits` param on `_impl_ask`; `_impl_discover` uses `_PickFirst` not LLM driver |
| `core/schema.py` | 100% | — |
| `core/llm/ollama.py` | 95% | `embed` model override param not surfaced to `AskConfig.embed_model` call chain (it is passed via `_OllamaEmbedAdapter`) — actually fine |
| `core/llm/claude.py` | 60% | Exists but not called from pipeline; `summarize.py` ignores `summarizer` config |
| `core/store/run.py` | 100% | — |
| `core/store/timeline.py` | 100% | — |
| `core/store/cache.py` | 100% | — |
| `core/store/reputation.py` | 95% | `auto_update` never called from the pipeline (reputation is loaded but never written back after a run) |
| `core/sources/reddit.py` | 100% | — |
| `core/sources/hn.py` | 85% | No zero-result warning; no comment fetch (HN posts don't have a comment API equivalent) |
| `core/sources/indiehackers.py` | 70% | Single category hardcoded; no keyword search; no zero-result warning; brittle CSS selectors |
| `core/sources/google_trends.py` | 75% | No `request_delay`; 429 is warn-and-continue not retry; pytrends fallback untested |
| `core/pipeline/discover_subs.py` | 75% | Discovery prompt doesn't prefer niche subs — root cause of sysadmin bug |
| `core/pipeline/rank.py` | 90% | `drop_threshold` default mismatch with `AskConfig`; threshold empirically unvalidated |
| `core/pipeline/summarize.py` | 90% | `summarizer="claude"` branch not implemented |
| `core/pipeline/narrate.py` | 90% | `# Digest` heading hardcoded; could echo topic as H1 |
| `core/pipeline/ask.py` | 85% | All three fixes from `TODO-tomorrow.md` are implemented in code but **not yet validated against a successful e2e run** |
| `core/pipeline/prompts.py` | 70% | `DISCOVER_SYSTEM` lacks niche-preference weighting |
| `core/agent/discover.py` | 70% | `smolagents.CodeAgent` not used; `_tool_top_trending_google` relies on private `._impl` attr; `summarize_across` tool from spec §9 not implemented |
