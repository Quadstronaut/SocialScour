# SocialScour — Execution Observations

Notes captured while running SocialScour end-to-end for the first time against live Ollama + real APIs. Each entry is dated and tagged with severity:

- **nit** — cosmetic / nice-to-have
- **annoyance** — works but adds friction
- **bug** — wrong behavior
- **blocker** — can't proceed
- **idea** — improvement / feature thought

Severity ranks "fix priority," not "user impact at scale."

---

## Run 1 — 2026-05-13, `scour ask "Linux server hardening audit tools" --window-days 90`

### Pre-run / setup phase

- **annoyance** — CLI defaults (`--out data`, cache at `cache/ollama_calls.sqlite`, reputation at `cache/reputation.json`) are all **relative paths**. Running `scour` from any directory other than the SocialScour repo root silently creates `data/` and `cache/` wherever you launched. Should either resolve relative to a package-installed config dir (e.g. `%LOCALAPPDATA%\social-scraper` on Windows, `~/.local/share/social-scraper` on Linux), or hard-fail with a clear message if no run-root is configured.
- **annoyance** — `Ollama not reachable` error message is good, but doesn't include *which* model was attempted. If the daemon is up but the requested model isn't pulled, the diagnostic would be confusing. Suggest: include model name and a hint to run `ollama list`.
- **nit** — `pyproject.toml` declares the script as `scour`, but the package description and README references mix `scour`, `scrape`, and `social-scraper`. Pick one canonical name and use it everywhere (docs, help text, error messages).
- **nit** — no `scour --version` visible at a glance. Helpful for bug reports.
- **idea** — `scour doctor` subcommand that runs all preflight checks (Ollama reachable, model pulled, network reachable, cache writable, sources responding) and emits a green-check / red-x report. This is exactly the kind of "demo-first" diagnostic that makes the tool feel professional on first run.
- **idea** — first-run UX: detect when there's no `data/` yet and print a one-line "Welcome — your runs will land in `<absolute path>`. Press Ctrl-C to cancel and configure via `scour init`."

### Discoverability / docs

- **annoyance** — figuring out the canonical CLI invocation required reading `cli.py` source. README should have a "Quick start" block:
  ```
  scour ask "your topic here"
  scour ask "topic" --window-days 60 --sources reddit,hn
  scour list
  scour timeline <slug>
  ```
- **idea** — `scour ask --help` could include a one-line example, not just argument descriptions.

### Runtime observations (filled in as the run progresses)

- **bug** — first invocation failed immediately with `ModuleNotFoundError: No module named 'social_scraper'`. The `scour.exe` shim at `C:\Users\Quadstronaut\scoop\apps\python\current\Scripts\scour.exe` was present (so `where scour` returned a path and looked installed), but the actual package was missing from site-packages. Likely cause: a prior `pip uninstall social-scraper` didn't remove the entry-point shim, or the install was in a different Python env. Fix was `pip install -e .` from the repo root. Implication for the user: there is no preflight check that the package is actually importable. Suggested fix: add a tiny startup check in `cli.py` that imports a sentinel symbol from `social_scraper.core` and prints a clear "Package not installed — run `pip install -e .` from the repo root" message instead of a raw traceback. Same `scour doctor` subcommand idea would catch this.
- **idea** — `scour doctor` should also warn when the installed package version doesn't match `pyproject.toml` — catches the "I forgot to reinstall after pulling new code" trap.

### Runtime — post-completion diagnosis

**Run summary**
- Query: `scour ask "Linux server hardening audit tools" --window-days 90`
- Duration: 18 min 17 sec (06:58:45 → 07:17:02 UTC)
- Sources: 1 of 4 produced data (Reddit only; HN + IH silently empty; Trends 429'd)
- Output: `data/runs/linux-server-hardening-audit-tools_2026-05-14T06-58-45Z/summary/summary.md`
- Verdict from the operator standpoint: **the summary did not answer the question.** It synthesized off-topic r/linux content (Vim vs Nano, Linux kernel anti-cheats, macOS-vs-Linux desktop polish) into a polished narrative that has zero overlap with the actual query.

**Critical findings (in rough priority order):**

- **blocker** — **Subreddit discovery is selecting the wrong subs.** For a niche sysadmin/security topic, the discovery stage landed on **r/linux** (general community) instead of r/sysadmin, r/selfhosted, r/linuxadmin, r/devops, or r/cybersecurity. Top "ranked" post was "Happy Birthday, Linus Torvalds" (18K upvotes in r/linux). Second was an unrelated political post about age-verification legislation. This makes the tool unusable for the user's stated decision-support use case (figuring out whether a product is worth building). Likely root cause: the LLM-driven discovery is keying off the word "Linux" without weighting the rest of the topic phrase. Fix candidates: (a) explicit `--subreddits` CLI flag to force-pin subs and bypass discovery for known-target queries; (b) a hard-coded "always include" list of sysadmin-relevant subs when topic matches infra keywords; (c) better discovery prompt that instructs the LLM to prefer specific/niche subs over flagship/general ones; (d) post-discovery validation step that rejects discovered subs whose top-30-day content doesn't word-match topic tokens.
- **blocker** — **Relevance ranker is not actually ranking by relevance.** The `ranked.jsonl` shows scores in perfect 0.05 descending steps (0.95, 0.90, 0.85, 0.80, ..., 0.25). That's not an LLM judgment — that's positional ranking emitting a synthetic descending score. The "Happy Birthday Linus" post got 0.95 for a query about server hardening. Need a real semantic-relevance gate (embedding similarity to topic, or LLM with explicit "is this about TOPIC: y/n + score 0-1" prompt with rationale).
- **blocker** — **No relevance check between final summary and original topic.** The summarizer happily synthesized whatever ranked posts came through, even when none addressed the topic. Need a final gate: "given the original topic and the ranked content, if <X% of ranked content addresses the topic, fail loudly: `topic_mismatch: ranked content does not address '<topic>'`." This would have produced a useful error here instead of a confidently-wrong summary.
- **bug** — **HN and IH silently produced zero usable data.** No warning, no diagnostic, just missing from `raw/`. Either the source clients returned empty results, the filtering rejected everything, or the deep-fetch stage failed. Add per-source counters to `meta.json`: `per_source_stats: {reddit: {discovered: N, ranked: M, deep_fetched: K}, hn: {...}}`. Right now you can't diagnose source-level failures from the run artifacts.
- **bug** — **Google Trends 429 handling is silent-skip.** The warning shows up in stdout but the summary doesn't acknowledge "Trends data unavailable for this run." If Trends is part of the pipeline, the summary should note when it's missing so the reader knows the digest is incomplete. Also: trendspy's own warning literally suggests `Trends(request_delay=2.0)` — the client should respect that automatically (add request_delay default, or backoff-and-retry once, before logging the failure).
- **annoyance** — **18 minutes per query is expensive when results are bad.** The pipeline runs the full deep-fetch + LLM summary even when the ranked input is garbage. A pre-LLM gate that checks "did we get usable content?" would save 10+ minutes per failed run.
- **annoyance** — **Discovery decisions aren't recorded.** `meta.json` should log which subs were considered and which were chosen, with the rationale (token overlap, LLM reasoning, traffic weight, etc.). Right now there's no way to audit *why* r/linux won.
- **annoyance** — **The ranker rationale isn't persisted.** `ranked.jsonl` has only `{post_id, source, relevance}`. Add `reason: "..."` so a human auditor can see why each item was scored where it was scored.
- **idea** — `scour ask --dry-run` flag: do everything up to LLM summarization, then dump the ranked candidates + relevance scores + sub choices, ask the user "does this look right? Proceed (y/N)?" — saves wasted LLM time on bad pipelines.
- **idea** — `--subreddits` flag to force a sub list, bypassing discovery. For decision-support use cases the user often knows the target communities better than an LLM does.
- **idea** — A `scour ask --explain` mode that emits a per-stage trace (discovery picks + rationale, per-source fetch counts, ranking decisions, summarizer prompt) so a debugger can see where the pipeline went off the rails.
- **idea** — A second pass: after the summary is generated, run a quick LLM check "does this summary actually answer the user's topic?" and emit a confidence score the user can see at the bottom of the markdown. Cheap, useful, would have flagged this run as a miss before the operator read it.

**Net assessment of SocialScour for the user's product-decision use case:**

The architecture is right and the test suite is real, but the live pipeline currently has a quality-control problem: it produces a confidently-written summary even when the inputs are wrong-topic. For an operator using this to decide what to build, that's worse than no answer — it could lead them to validate a false signal. Recommended sequence before another product-decision query: fix subreddit discovery (force-pin or LLM-prompt-tune), fix the ranker (real semantic relevance), add a topic-relevance gate before summarization. The Stream 2 audit was right that this was ~80% done; this run shows the remaining 20% includes three load-bearing correctness bugs, not just polish.

