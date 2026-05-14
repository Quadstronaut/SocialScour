# TODO — Tomorrow's SocialScour Fix Session

Goal: get SocialScour producing trustworthy results for product-decision queries. After last night's 2026-05-14 e2e run produced a confidently-wrong off-topic summary, three load-bearing bugs need to be addressed before the tool is usable for the portfolio strategy work.

**Full diagnostic is in `execution-observations.md`.** This file is the prioritized fix plan only.

---

## Session plan (estimated 4–6 focused hours)

### 1. Quick win — add `--subreddits` CLI flag (~30 min)

Force-pin subs from the command line, bypassing the broken discovery stage.

- [ ] Add `--subreddits` option to `scour ask` in `social_scraper/cli.py` (comma-separated, e.g. `--subreddits sysadmin,selfhosted,linuxadmin`)
- [ ] Plumb through `AskConfig` to skip discovery when this flag is set
- [ ] Document: "Use this when you already know which communities discuss the topic — bypasses LLM-driven discovery."
- [ ] Unit test: assert discovery is skipped when `subreddits` is set.

**Why first:** unblocks dogfooding *today* without solving the underlying discovery bug. You can run validation queries against the right subs by hand-picking them.

### 2. Real semantic relevance ranking (~2–3 hours)

Replace the current synthetic 0.05-step descending ranking with actual relevance scoring.

- [ ] Pick the implementation: **embeddings-based** (use `bge-m3:latest` which is already pulled — cosine-sim between topic and `title + first 200 chars of body`) is the cleanest. LLM "score it 0-1 with rationale" is fallback. Embeddings is faster, deterministic, and cheap.
- [ ] Replace whatever currently writes `ranked.jsonl` with a real scoring stage. Persist `{post_id, source, relevance, reason}` so the score is auditable.
- [ ] Set a **drop threshold** (suggest 0.55 cosine, tune empirically): anything below this never makes it to summarization.
- [ ] Add per-source counters to `meta.json`: `per_source_stats: {reddit: {discovered: N, ranked: M, kept: K, dropped: D}, hn: {...}}`. Drives the next fix.
- [ ] Unit test: rank a known-relevant + known-irrelevant pair, assert relevant scores higher.

**Why second:** even with the right subs, you need actual relevance scoring or you'll keep dragging noise into the summary. Embeddings here pays for itself for every future query.

### 3. Topic-relevance gate before summarization (~1 hour)

Final correctness check: if too few posts actually addressed the topic, fail the summary rather than synthesize one.

- [ ] After ranking + threshold filtering, count kept posts. If `kept < 5` OR `kept / discovered < 0.10`, fail the run with `topic_mismatch: only N of M posts addressed '<topic>'` and skip the expensive LLM summarization.
- [ ] On successful summary, run one cheap LLM call (qwen3:8b is fine here) asking: *"Does the following summary actually answer this question: '{topic}'? Reply JSON: `{addressed: bool, confidence: 0-1, rationale: '...'}`."* Persist into `meta.json` and prepend a one-line header to `summary.md`: `> topic-confidence: 0.87 — summary addresses query directly` (or `> ⚠ topic-confidence: 0.34 — summary may not address the original query` if low).
- [ ] Unit test: feed a known-off-topic synthetic corpus through, assert `topic_mismatch` is raised.

**Why third:** the polished off-topic summary problem is the worst failure mode — confidently wrong is worse than no answer. This is the last line of defense.

---

## Validation that the fixes worked

After all three are done, re-run the original query that failed last night:

```
scour ask "Linux server hardening audit tools" --window-days 90 \
  --subreddits sysadmin,selfhosted,linuxadmin,devops,cybersecurity
```

**Acceptance criteria:**

- [ ] Summary explicitly mentions Lynis, OpenSCAP, Tiger, or similar named tools (proves on-topic content was retrieved)
- [ ] `meta.json` shows per-source counters (proves stats wiring)
- [ ] `summary.md` has a topic-confidence header (proves the final gate runs)
- [ ] Run completes in under 15 minutes (proves the gate short-circuits when it should)

If those four boxes check, SocialScour is ready to validate product #2 selection.

---

## Deferred (not in tomorrow's session)

Smaller items from `execution-observations.md` — handle these only after the three blockers ship:

- `scour doctor` preflight subcommand (Ollama reachable, model pulled, package importable, etc.)
- Absolute-path resolution for `--out`, cache, reputation defaults (so `scour` works from any CWD)
- Trends client default `request_delay=2.0` + one auto-backoff retry
- HN/IH zero-result warnings (when those sources fetch nothing, say so)
- `--dry-run` flag to dump ranked candidates before LLM summarization
- `--explain` flag with per-stage trace
- README "Quick start" block with the canonical CLI invocation
- `scour --version`
- Ranker rationale persistence (`reason: "..."` in `ranked.jsonl`)

These are all worth doing but none of them are between you and trustworthy results.

---

## Notes from last night

- The 18-minute runtime for a wrong-answer run was painful. Most of that was the final LLM summarization on garbage input. The topic-relevance gate (fix #3) plus the "fail if kept < 5" check should reduce wasted-LLM time on bad pipelines to near zero.
- `bge-m3:latest` is already pulled (1.2 GB, 6 days ago) — no model download needed for fix #2.
- The test suite is solid (52/52 passing). Adding tests for the three fixes follows the existing patterns; nothing structural to learn.
