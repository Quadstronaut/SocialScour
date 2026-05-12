# Social Scraper v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-source social aggregator (Reddit + Google Trends + HN + IndieHackers) with two entry points (Ollama CLI + Claude Code MCP server) and two modes (deterministic `ask`, agentic `discover`), per the spec at `docs/superpowers/specs/2026-05-11-social-scraper-v2-design.md`.

**Architecture:** New `social_scraper/` Python package at repo root. Bottom-up build: schema → llm clients → store → sources → pipeline → agent → cli/mcp. Each layer fully tested before the next. Ports from `dev-testing/claude/reddit_research/` where useful; rewrites `rank.py` for strict-JSON Ollama mode.

**Tech Stack:** Python 3.11+, httpx, pydantic v2, tenacity, typer, beautifulsoup4, trendspyg, smolagents, mcp, vcrpy (dev), pytest + pytest-repeat (dev).

**Hard rules baked into this plan (from operator memory):**
1. Every layer (component/workflow/e2e) must pass 3 consecutive times with zero errors before that layer is "done." Tasks with a 3x gate state this explicitly.
2. User is unattended during execution — if a task is blocked, stop and write a status note in `docs/superpowers/plans/STATUS.md` for the operator to find on return. Do not paper over.
3. Commit after every task. No big bang commits.

---

## File Structure

Created or modified by this plan:

```
RedditScraper/
├── .gitignore                                   # MODIFY (Task 1)
├── pyproject.toml                               # CREATE (Task 1)
├── social_scraper/
│   ├── __init__.py                              # CREATE (Task 1)
│   ├── cli.py                                   # CREATE (Task 19)
│   ├── mcp_server.py                            # CREATE (Task 20)
│   └── core/
│       ├── __init__.py                          # CREATE (Task 1)
│       ├── schema.py                            # CREATE (Task 2)
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── ollama.py                        # CREATE (Task 3)
│       │   └── claude.py                        # CREATE (Task 4)
│       ├── store/
│       │   ├── __init__.py
│       │   ├── run.py                           # CREATE (Task 5)
│       │   ├── timeline.py                      # CREATE (Task 6)
│       │   ├── cache.py                         # CREATE (Task 7)
│       │   └── reputation.py                    # PORT (Task 8)
│       ├── sources/
│       │   ├── __init__.py
│       │   ├── reddit.py                        # PORT (Task 9)
│       │   ├── google_trends.py                 # CREATE (Task 10)
│       │   ├── hn.py                            # CREATE (Task 11)
│       │   └── indiehackers.py                  # CREATE (Task 12)
│       ├── pipeline/
│       │   ├── __init__.py
│       │   ├── discover_subs.py                 # PORT (Task 13)
│       │   ├── rank.py                          # REWRITE (Task 14)
│       │   ├── summarize.py                     # CREATE (Task 15)
│       │   ├── narrate.py                       # CREATE (Task 16)
│       │   └── ask.py                           # CREATE (Task 17)
│       └── agent/
│           ├── __init__.py
│           └── discover.py                      # CREATE (Task 18)
└── tests/
    ├── __init__.py
    ├── conftest.py                              # CREATE (Task 1)
    ├── component/
    │   ├── fixtures/                            # ported + new fixtures
    │   ├── test_schema.py                       # Task 2
    │   ├── test_llm_ollama.py                   # Task 3
    │   ├── test_llm_claude.py                   # Task 4
    │   ├── test_store_run.py                    # Task 5
    │   ├── test_store_timeline.py               # Task 6
    │   ├── test_store_cache.py                  # Task 7
    │   ├── test_store_reputation.py             # Task 8
    │   ├── test_sources_reddit.py               # Task 9
    │   ├── test_sources_google_trends.py        # Task 10
    │   ├── test_sources_hn.py                   # Task 11
    │   ├── test_sources_indiehackers.py         # Task 12
    │   ├── test_pipeline_discover_subs.py       # Task 13
    │   ├── test_pipeline_rank.py                # Task 14
    │   ├── test_pipeline_summarize.py           # Task 15
    │   ├── test_pipeline_narrate.py             # Task 16
    │   └── test_agent_discover.py               # Task 18 (tool functions only)
    ├── workflow/
    │   ├── test_pipeline_ask.py                 # Task 17
    │   ├── test_agent_discover_loop.py          # Task 18
    │   ├── test_cli.py                          # Task 19
    │   └── test_mcp_server.py                   # Task 20
    └── e2e/
        └── test_real_ask.py                     # Task 22
```

---

## Task 0: Cleanup commit — consolidate old layout into `dev-testing/`

The repo currently has unstaged deletions of the old bake-off layout (`aider/`, `claude/`, root logs, runner stubs) plus an untracked `dev-testing/` that holds the moved code. Commit this before any new work so the new code sits on a clean baseline.

**Files:**
- Stage: all current deletions + untracked `dev-testing/`
- Modify: none (just a reorg commit)

- [ ] **Step 1: Verify the move is clean**

Run: `git -C "P:\Documents\GIT\RedditScraper" status -s`

Expected: deletions cover `aider/`, `aider-test/`, `claude/`, `goose.ps1`, `opencode.ps1`, `aider.ps1`, `build-prompt.md`, `build-with-ollama.py`, `v1.spec`, and the `aider-*.log` files. Untracked: `dev-testing/`.

If there are extra modifications or different files, STOP and write a status note to `docs/superpowers/plans/STATUS.md` explaining the discrepancy.

- [ ] **Step 2: Stage everything in this reorg**

Run:
```powershell
git -C "P:\Documents\GIT\RedditScraper" add -A aider/ aider-test/ claude/ goose.ps1 opencode.ps1 aider.ps1 aider-test.ps1 build-prompt.md build-with-ollama.py v1.spec aider-raw-031624.log aider-run-031624.log aider-run-191243.log aider-test-raw-024407.log aider-test-raw-024623.log aider-test-run-024407.log aider-test-run-024623.log aider-test-run-230639.log aider-test-spec.md dev-testing/
```

- [ ] **Step 3: Commit**

Run:
```powershell
git -C "P:\Documents\GIT\RedditScraper" commit -m "Move bake-off scratch into dev-testing/

Old aider/, claude/, and aider-test/ packages plus their runner stubs and
logs are consolidated under dev-testing/ as reference material for the v2
build. No code is deleted — only relocated.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Verify**

Run: `git -C "P:\Documents\GIT\RedditScraper" status -s`
Expected: empty output (clean tree).

---

## Task 1: Project skeleton + pyproject.toml + gitignore + test config

**Files:**
- Create: `social_scraper/__init__.py`
- Create: `social_scraper/core/__init__.py`
- Create: `social_scraper/core/llm/__init__.py`
- Create: `social_scraper/core/store/__init__.py`
- Create: `social_scraper/core/sources/__init__.py`
- Create: `social_scraper/core/pipeline/__init__.py`
- Create: `social_scraper/core/agent/__init__.py`
- Create: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/component/__init__.py`
- Create: `tests/workflow/__init__.py`
- Create: `tests/e2e/__init__.py`
- Create: `tests/component/fixtures/__init__.py`
- Modify or create: `.gitignore`

- [ ] **Step 1: Create directory tree**

Run:
```powershell
New-Item -ItemType Directory -Force -Path `
  'social_scraper\core\llm', `
  'social_scraper\core\store', `
  'social_scraper\core\sources', `
  'social_scraper\core\pipeline', `
  'social_scraper\core\agent', `
  'tests\component\fixtures', `
  'tests\workflow', `
  'tests\e2e' | Out-Null
```

- [ ] **Step 2: Create empty `__init__.py` files**

Create each of these as empty files:
- `social_scraper/__init__.py` with content `"""Social scraper v2."""\n`
- `social_scraper/core/__init__.py`
- `social_scraper/core/llm/__init__.py`
- `social_scraper/core/store/__init__.py`
- `social_scraper/core/sources/__init__.py`
- `social_scraper/core/pipeline/__init__.py`
- `social_scraper/core/agent/__init__.py`
- `tests/__init__.py`
- `tests/component/__init__.py`
- `tests/component/fixtures/__init__.py`
- `tests/workflow/__init__.py`
- `tests/e2e/__init__.py`

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "social-scraper"
version = "0.2.0"
description = "Multi-source social aggregator (Reddit, Google Trends, HN, IndieHackers) with Ollama + Claude Code drivers."
requires-python = ">=3.11"
dependencies = [
    "httpx[http2]>=0.27",
    "pydantic>=2.7",
    "tenacity>=8.3",
    "typer>=0.12",
    "beautifulsoup4>=4.12",
    "trendspy>=0.1.6",
    "smolagents>=1.0",
    "mcp>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
    "pytest-repeat>=0.9",
    "vcrpy>=6.0",
]

[project.scripts]
scrape = "social_scraper.cli:app"
social-scraper-mcp = "social_scraper.mcp_server:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["social_scraper*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "component: isolated unit tests (no network)",
    "workflow: full-pipeline tests with fakes (no network)",
    "e2e: real services — requires --e2e flag",
]
addopts = "-ra --strict-markers -m 'not e2e'"
```

Note on `trendspyg`: PyPI name is `trendspy` (some refs call it TrendsPyG); confirm package name on `pip install` and adjust if the install fails. If `trendspy` is unavailable on PyPI, fall back to `pytrends` and note the deviation in `docs/superpowers/plans/STATUS.md`.

- [ ] **Step 4: Write `tests/conftest.py`**

```python
"""Shared pytest fixtures and configuration."""
from __future__ import annotations

from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption("--e2e", action="store_true", help="run e2e tests")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--e2e"):
        # remove the default -m 'not e2e' filter would still apply; let users invoke with `-m e2e`
        return
    skip_e2e = pytest.mark.skip(reason="needs --e2e")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_e2e)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "component" / "fixtures"
```

- [ ] **Step 5: Write `.gitignore`**

If `.gitignore` exists, append; if not, create with:

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.venv/
venv/

# Scraper outputs (per spec §7 — never sync)
data/
cache/

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 6: Install editable + run pytest smoke**

Run:
```powershell
python -m pip install -e .[dev]
pytest -q
```

Expected: pytest collects 0 tests (no test files yet), exits 5 (no tests collected) — acceptable for the skeleton stage. If pip install fails on `trendspy`, see step 3 note.

- [ ] **Step 7: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add pyproject.toml .gitignore social_scraper/ tests/
git -C "P:\Documents\GIT\RedditScraper" commit -m "Scaffold social_scraper package + test config

Creates the social_scraper/ Python package with core/{llm,store,sources,pipeline,agent}/
subpackages, pyproject.toml with pinned deps, and a tests/ tree with
component/workflow/e2e markers. data/ and cache/ gitignored per spec §7.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Pydantic schemas (`core/schema.py`)

**Files:**
- Create: `social_scraper/core/schema.py`
- Test: `tests/component/test_schema.py`

- [ ] **Step 1: Write the failing test**

Create `tests/component/test_schema.py`:

```python
"""Tests for pydantic models in social_scraper.core.schema."""
from __future__ import annotations

import pytest

from social_scraper.core.schema import (
    Digest,
    PostSummary,
    RawComment,
    RawPost,
    RunMeta,
    SourceKind,
)


pytestmark = pytest.mark.component


def test_source_kind_values():
    assert {s.value for s in SourceKind} == {"reddit", "hn", "indiehackers", "google_trends"}


def test_raw_post_roundtrip():
    post = RawPost(
        source=SourceKind.reddit,
        id="abc",
        url="https://example.com/abc",
        title="hello",
        author="user1",
        body="body text",
        score=42,
        num_comments=5,
        created_utc=1700000000.0,
        subreddit="test",
    )
    data = post.model_dump()
    assert RawPost.model_validate(data) == post


def test_raw_comment_defaults():
    c = RawComment(id="x", body="hi", score=1, created_utc=1.0)
    assert c.author is None
    assert c.depth == 0


def test_post_summary_relevance_bounds():
    with pytest.raises(ValueError):
        PostSummary(
            post_id="x",
            source=SourceKind.reddit,
            summary="s",
            themes=["t"],
            relevance_to_prompt=1.5,
        )


def test_digest_minimum():
    d = Digest(
        prompt="x",
        generated_utc="2026-05-11T00:00:00Z",
        sources_used=[SourceKind.reddit],
        item_count=0,
        themes=[],
        narrative="",
    )
    assert d.item_count == 0


def test_run_meta_warnings_default_empty():
    m = RunMeta(
        topic="x",
        slug="x",
        window_days=30,
        sources=[SourceKind.reddit],
        model="qwen3-coder:30b",
        summarizer="ollama",
        started_utc="2026-05-11T00:00:00Z",
    )
    assert m.warnings == []
    assert m.finished_utc is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/component/test_schema.py -v`
Expected: collection error or ImportError — module doesn't exist yet.

- [ ] **Step 3: Implement `social_scraper/core/schema.py`**

```python
"""Pydantic models shared across the scraper."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SourceKind(str, Enum):
    reddit = "reddit"
    hn = "hn"
    indiehackers = "indiehackers"
    google_trends = "google_trends"


class RawComment(BaseModel):
    id: str
    author: Optional[str] = None
    body: str
    score: int
    created_utc: float
    depth: int = 0
    parent_id: Optional[str] = None


class RawPost(BaseModel):
    source: SourceKind
    id: str
    url: str
    title: str
    author: Optional[str] = None
    body: str = ""
    score: int = 0
    num_comments: int = 0
    created_utc: float
    # Reddit-specific (optional everywhere else)
    subreddit: Optional[str] = None
    permalink: Optional[str] = None
    upvote_ratio: Optional[float] = None
    is_self: Optional[bool] = None
    flair: Optional[str] = None
    top_comments: list[RawComment] = Field(default_factory=list)


class PostSummary(BaseModel):
    post_id: str
    source: SourceKind
    summary: str
    themes: list[str] = Field(default_factory=list)
    relevance_to_prompt: float = Field(ge=0.0, le=1.0, default=0.0)


class SourceSentiment(BaseModel):
    source: SourceKind
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    n_posts: int = 0
    n_comments: int = 0
    theme: str = ""


class NotablePost(BaseModel):
    post_id: str
    source: SourceKind
    url: str
    title: str
    why: str


class Digest(BaseModel):
    prompt: str
    generated_utc: str
    sources_used: list[SourceKind]
    item_count: int
    themes: list[str] = Field(default_factory=list)
    narrative: str
    notable_posts: list[NotablePost] = Field(default_factory=list)
    per_source_sentiment: list[SourceSentiment] = Field(default_factory=list)


class RunMeta(BaseModel):
    topic: str
    slug: str
    window_days: int
    sources: list[SourceKind]
    model: str
    summarizer: str  # "ollama" | "claude"
    started_utc: str
    finished_utc: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    blocked_sources: list[SourceKind] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/component/test_schema.py -v`
Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/schema.py tests/component/test_schema.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add core pydantic schema (RawPost, PostSummary, Digest, RunMeta)

Multi-source schema: SourceKind enum covers reddit/hn/indiehackers/google_trends.
RawPost is the lingua franca; source-specific fields (subreddit, permalink)
are optional. PostSummary.relevance_to_prompt is bounded 0..1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Ollama client with strict-JSON mode + repair pass (`core/llm/ollama.py`)

This is the rewrite that prevents the dev-testing/claude G5 failure (rank.py malformed JSON). Per spec §10.

**Files:**
- Create: `social_scraper/core/llm/ollama.py`
- Test: `tests/component/test_llm_ollama.py`

- [ ] **Step 1: Write the failing test**

Create `tests/component/test_llm_ollama.py`:

```python
"""Tests for OllamaClient JSON-mode + repair pass."""
from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from social_scraper.core.llm.ollama import OllamaClient, OllamaError


pytestmark = pytest.mark.component


class _Toy(BaseModel):
    x: int
    label: str


def _mock_transport(responses: list[str]) -> httpx.MockTransport:
    """Return a MockTransport that yields each response body in order, all 200."""
    idx = {"i": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        i = idx["i"]
        idx["i"] += 1
        body = responses[min(i, len(responses) - 1)]
        return httpx.Response(200, json={"message": {"content": body}})

    return httpx.MockTransport(handler)


def test_json_call_happy_path():
    client = OllamaClient(
        model="fake",
        http_client=httpx.Client(transport=_mock_transport([json.dumps({"x": 1, "label": "ok"})])),
    )
    result = client.json_call("sys", "user", _Toy)
    assert result == _Toy(x=1, label="ok")


def test_json_call_repair_pass():
    # First response: malformed JSON. Second response: valid.
    client = OllamaClient(
        model="fake",
        http_client=httpx.Client(transport=_mock_transport([
            "Here's the JSON: {\"x\": 2, \"label\": \"ok\"} hope that helps",
            json.dumps({"x": 2, "label": "ok"}),
        ])),
    )
    result = client.json_call("sys", "user", _Toy)
    assert result.x == 2


def test_json_call_double_fail_raises():
    client = OllamaClient(
        model="fake",
        http_client=httpx.Client(transport=_mock_transport([
            "garbage one",
            "garbage two",
        ])),
    )
    with pytest.raises(OllamaError):
        client.json_call("sys", "user", _Toy)


def test_ping_true_when_models_returned():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "qwen3-coder:30b"}]})
    client = OllamaClient(
        model="qwen3-coder:30b",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.ping() is True


def test_ping_false_on_transport_error():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no", request=req)
    client = OllamaClient(
        model="x",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.ping() is False


def test_chat_returns_plain_text():
    client = OllamaClient(
        model="fake",
        http_client=httpx.Client(transport=_mock_transport(["hello world"])),
    )
    assert client.chat("sys", "user") == "hello world"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/component/test_llm_ollama.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `social_scraper/core/llm/ollama.py`**

```python
"""Ollama JSON-mode client with one repair retry."""
from __future__ import annotations

import json
import os
import re
from typing import Iterator, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class OllamaError(Exception):
    pass


def _default_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


# Pull a JSON object from arbitrary text (greedy match on outermost braces).
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> Optional[str]:
    m = _JSON_OBJECT_RE.search(text)
    return m.group(0) if m else None


class OllamaClient:
    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url or _default_base_url()
        self._http = http_client or httpx.Client(timeout=timeout)
        self._owns_http = http_client is None

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def ping(self) -> bool:
        try:
            resp = self._http.get(f"{self.base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def chat(self, system: str, user: str) -> str:
        resp = self._http.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def chat_stream(self, system: str, user: str) -> Iterator[str]:
        with self._http.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "stream": True,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = obj.get("message", {}).get("content")
                if msg:
                    yield msg

    def json_call(self, system: str, user: str, model_cls: Type[T]) -> T:
        """Call Ollama in JSON mode; on parse failure, do one repair retry then raise."""
        schema_json = model_cls.model_json_schema()
        sys_prompt = (
            f"{system}\n\n"
            f"Return JSON conforming exactly to this schema:\n{json.dumps(schema_json)}\n"
            f"Return ONLY the JSON object. No prose, no markdown fences."
        )
        first = self._json_call_once(sys_prompt, user)
        parsed = _try_parse(first, model_cls)
        if parsed is not None:
            return parsed
        # Repair pass.
        repair_user = (
            f"Your previous reply was not valid JSON for the schema. "
            f"Return ONLY the JSON object, no commentary.\n\nYour previous reply:\n{first}"
        )
        second = self._json_call_once(sys_prompt, repair_user)
        parsed2 = _try_parse(second, model_cls)
        if parsed2 is not None:
            return parsed2
        raise OllamaError(
            f"Could not parse JSON for schema {model_cls.__name__} after repair attempt. "
            f"Last reply: {second[:200]}"
        )

    def _json_call_once(self, system: str, user: str) -> str:
        resp = self._http.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


def _try_parse(text: str, model_cls: Type[T]) -> Optional[T]:
    candidates = [text]
    extracted = _extract_json(text)
    if extracted and extracted != text:
        candidates.append(extracted)
    for cand in candidates:
        try:
            return model_cls.model_validate_json(cand)
        except (ValidationError, ValueError):
            continue
    return None
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/component/test_llm_ollama.py -v`
Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/llm/ollama.py tests/component/test_llm_ollama.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add OllamaClient with strict-JSON mode + repair retry

json_call() uses Ollama format:json, renders the pydantic schema into the
system prompt, and retries once with the malformed text fed back before
raising. Closes the failure class that triggered ProductResearch G5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Claude CLI subprocess client (`core/llm/claude.py`)

**Files:**
- Create: `social_scraper/core/llm/claude.py`
- Test: `tests/component/test_llm_claude.py`

- [ ] **Step 1: Write the failing test**

Create `tests/component/test_llm_claude.py`:

```python
"""Tests for ClaudeClient subprocess wrapper."""
from __future__ import annotations

import subprocess

import pytest

from social_scraper.core.llm.claude import ClaudeClient, ClaudeError


pytestmark = pytest.mark.component


def test_summarize_calls_claude_p(mocker):
    run = mocker.patch(
        "social_scraper.core.llm.claude.subprocess.run",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="OK\n", stderr=""),
    )
    client = ClaudeClient()
    out = client.summarize("text to summarize", "prompt context")
    assert out == "OK"
    args, kwargs = run.call_args
    cmd = args[0]
    assert cmd[0] == "claude"
    assert "-p" in cmd


def test_summarize_raises_on_nonzero(mocker):
    mocker.patch(
        "social_scraper.core.llm.claude.subprocess.run",
        return_value=subprocess.CompletedProcess(args=[], returncode=2, stdout="", stderr="boom"),
    )
    client = ClaudeClient()
    with pytest.raises(ClaudeError):
        client.summarize("x", "y")


def test_summarize_raises_when_claude_not_installed(mocker):
    mocker.patch(
        "social_scraper.core.llm.claude.subprocess.run",
        side_effect=FileNotFoundError(),
    )
    client = ClaudeClient()
    with pytest.raises(ClaudeError):
        client.summarize("x", "y")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/component/test_llm_claude.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `social_scraper/core/llm/claude.py`**

```python
"""Thin wrapper around the `claude` CLI for summarization override."""
from __future__ import annotations

import subprocess


class ClaudeError(Exception):
    pass


class ClaudeClient:
    def __init__(self, executable: str = "claude", timeout_s: int = 300) -> None:
        self._exe = executable
        self._timeout = timeout_s

    def summarize(self, text: str, prompt_context: str) -> str:
        full_prompt = (
            f"{prompt_context}\n\n"
            f"---\n"
            f"Summarize the following content in 3-5 sentences. Stay factual.\n\n"
            f"{text}"
        )
        try:
            proc = subprocess.run(
                [self._exe, "-p", full_prompt],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except FileNotFoundError as exc:
            raise ClaudeError(
                f"`{self._exe}` not found on PATH. Install Claude Code CLI or pass executable=..."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ClaudeError(f"claude CLI timed out after {self._timeout}s") from exc

        if proc.returncode != 0:
            raise ClaudeError(
                f"claude CLI exited {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc.stdout.strip()
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/component/test_llm_claude.py -v`
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/llm/claude.py tests/component/test_llm_claude.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add ClaudeClient subprocess wrapper for --summarizer=claude override

Shells out to \`claude -p\`. Raises ClaudeError on missing binary, timeout,
or nonzero exit. No SDK dependency in v1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Per-run folder writer (`core/store/run.py`)

**Files:**
- Create: `social_scraper/core/store/run.py`
- Test: `tests/component/test_store_run.py`

- [ ] **Step 1: Write the failing test**

Create `tests/component/test_store_run.py`:

```python
"""Tests for store.run."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from social_scraper.core.schema import RawPost, RunMeta, SourceKind
from social_scraper.core.store.run import RunWriter, slugify


pytestmark = pytest.mark.component


def test_slugify_basics():
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("AI/ML  trends — 2026") == "ai-ml-trends-2026"
    assert len(slugify("x" * 200)) <= 60


def test_run_writer_creates_layout(tmp_path):
    started = datetime(2026, 5, 11, 14, 22, 3, tzinfo=timezone.utc)
    writer = RunWriter(
        root=tmp_path,
        topic="vibecoding",
        sources=[SourceKind.reddit, SourceKind.hn],
        window_days=30,
        model="qwen3-coder:30b",
        summarizer="ollama",
        started=started,
    )
    assert writer.run_dir.name == "vibecoding_2026-05-11T14-22-03Z"
    assert (writer.run_dir / "raw").is_dir()
    assert (writer.run_dir / "summary").is_dir()
    assert (writer.run_dir / "meta.json").is_file()
    meta = json.loads((writer.run_dir / "meta.json").read_text())
    assert meta["topic"] == "vibecoding"
    assert meta["slug"] == "vibecoding"


def test_run_writer_appends_raw_jsonl(tmp_path):
    started = datetime(2026, 5, 11, tzinfo=timezone.utc)
    writer = RunWriter(
        root=tmp_path, topic="x", sources=[SourceKind.reddit],
        window_days=7, model="m", summarizer="ollama", started=started,
    )
    post = RawPost(
        source=SourceKind.reddit, id="abc", url="u", title="t",
        created_utc=1.0, subreddit="test",
    )
    writer.write_raw(SourceKind.reddit, [post])
    line = (writer.run_dir / "raw" / "reddit.jsonl").read_text().strip()
    assert json.loads(line)["id"] == "abc"


def test_run_writer_writes_summary_and_finalizes(tmp_path):
    started = datetime(2026, 5, 11, tzinfo=timezone.utc)
    writer = RunWriter(
        root=tmp_path, topic="x", sources=[SourceKind.reddit],
        window_days=7, model="m", summarizer="ollama", started=started,
    )
    writer.write_summary_md("# Summary\n\nSome text.")
    writer.add_warning("rank_fallback_used")
    finished = datetime(2026, 5, 11, 0, 1, 0, tzinfo=timezone.utc)
    writer.finalize(finished=finished)
    meta = json.loads((writer.run_dir / "meta.json").read_text())
    assert meta["finished_utc"] == "2026-05-11T00:01:00Z"
    assert "rank_fallback_used" in meta["warnings"]
    summary = (writer.run_dir / "summary" / "summary.md").read_text()
    assert summary.startswith("# Summary")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/component/test_store_run.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `social_scraper/core/store/run.py`**

```python
"""Per-run folder writer."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel

from social_scraper.core.schema import RawPost, RunMeta, SourceKind


_SLUG_MAX = 60
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    s = text.lower()
    s = _NON_ALNUM.sub("-", s).strip("-")
    return s[:_SLUG_MAX].rstrip("-")


def _utc_stamp(dt: datetime) -> str:
    # Filesystem-safe: replace ':' with '-' in the time portion.
    return dt.strftime("%Y-%m-%dT%H-%M-%SZ")


def _iso_z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class RunWriter:
    def __init__(
        self,
        root: Path,
        topic: str,
        sources: list[SourceKind],
        window_days: int,
        model: str,
        summarizer: str,
        started: datetime,
    ) -> None:
        self.root = Path(root)
        self.topic = topic
        self.slug = slugify(topic) or "untitled"
        self.started = started
        self.run_dir = self.root / "runs" / f"{self.slug}_{_utc_stamp(started)}"
        (self.run_dir / "raw").mkdir(parents=True, exist_ok=True)
        (self.run_dir / "summary").mkdir(parents=True, exist_ok=True)
        self.meta = RunMeta(
            topic=topic,
            slug=self.slug,
            window_days=window_days,
            sources=list(sources),
            model=model,
            summarizer=summarizer,
            started_utc=_iso_z(started),
        )
        self._write_meta()

    def _write_meta(self) -> None:
        (self.run_dir / "meta.json").write_text(self.meta.model_dump_json(indent=2))

    def write_raw(self, source: SourceKind, items: Iterable[BaseModel | RawPost]) -> None:
        path = self.run_dir / "raw" / f"{source.value}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            for item in items:
                f.write(item.model_dump_json() + "\n")

    def write_raw_blob(self, source: SourceKind, payload: dict) -> None:
        path = self.run_dir / "raw" / f"{source.value}.json"
        path.write_text(json.dumps(payload, indent=2))

    def write_ranked(self, ranked: list[dict]) -> None:
        path = self.run_dir / "ranked.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for r in ranked:
                f.write(json.dumps(r) + "\n")

    def write_summary_md(self, text: str) -> None:
        (self.run_dir / "summary" / "summary.md").write_text(text, encoding="utf-8")

    def add_warning(self, warning: str) -> None:
        self.meta.warnings.append(warning)
        self._write_meta()

    def mark_blocked(self, source: SourceKind) -> None:
        if source not in self.meta.blocked_sources:
            self.meta.blocked_sources.append(source)
            self._write_meta()

    def finalize(self, finished: datetime) -> None:
        self.meta.finished_utc = _iso_z(finished)
        self._write_meta()
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/component/test_store_run.py -v`
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/store/run.py tests/component/test_store_run.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add RunWriter for per-run folder layout

Writes data/runs/<slug>_<utc>/{meta.json, raw/<source>.jsonl, summary/summary.md, ranked.jsonl}
per spec §7. UTC stamp is filesystem-safe (colons replaced).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Topic timeline appender (`core/store/timeline.py`)

**Files:**
- Create: `social_scraper/core/store/timeline.py`
- Test: `tests/component/test_store_timeline.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for store.timeline."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from social_scraper.core.store.timeline import TimelineWriter


pytestmark = pytest.mark.component


def test_first_append_creates_file(tmp_path):
    tw = TimelineWriter(root=tmp_path, slug="vibecoding")
    tw.append(
        when=datetime(2026, 5, 11, 14, 0, 0, tzinfo=timezone.utc),
        run_dir=tmp_path / "runs" / "vibecoding_2026-05-11T14-00-00Z",
        verdict="First paragraph of the narrative.",
    )
    path = tmp_path / "topics" / "vibecoding" / "timeline.md"
    assert path.is_file()
    text = path.read_text()
    assert "# vibecoding" in text
    assert "## 2026-05-11T14:00:00Z" in text
    assert "First paragraph" in text


def test_second_append_keeps_h1_and_adds_new_h2(tmp_path):
    tw = TimelineWriter(root=tmp_path, slug="vibe")
    tw.append(
        when=datetime(2026, 5, 11, tzinfo=timezone.utc),
        run_dir=tmp_path / "runs" / "vibe_2026-05-11T00-00-00Z",
        verdict="V1",
    )
    tw.append(
        when=datetime(2026, 5, 12, tzinfo=timezone.utc),
        run_dir=tmp_path / "runs" / "vibe_2026-05-12T00-00-00Z",
        verdict="V2",
    )
    text = (tmp_path / "topics" / "vibe" / "timeline.md").read_text()
    assert text.count("# vibe\n") == 1
    assert "## 2026-05-11T00:00:00Z" in text
    assert "## 2026-05-12T00:00:00Z" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/component/test_store_timeline.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `social_scraper/core/store/timeline.py`:

```python
"""Per-topic timeline appender."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


def _iso_z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class TimelineWriter:
    def __init__(self, root: Path, slug: str) -> None:
        self.root = Path(root)
        self.slug = slug
        self.path = self.root / "topics" / slug / "timeline.md"

    def append(self, when: datetime, run_dir: Path, verdict: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(f"# {self.slug}\n\n", encoding="utf-8")
        rel = self._relative_run_link(run_dir)
        block = (
            f"## {_iso_z(when)}\n\n"
            f"[Run folder]({rel})\n\n"
            f"{verdict.strip()}\n\n"
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(block)

    def _relative_run_link(self, run_dir: Path) -> str:
        try:
            return str(Path("..") / ".." / "runs" / run_dir.name).replace("\\", "/")
        except ValueError:
            return str(run_dir).replace("\\", "/")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/component/test_store_timeline.py -v`
Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/store/timeline.py tests/component/test_store_timeline.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add TimelineWriter — append H2 block per run to topics/<slug>/timeline.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: SQLite LLM-call cache (`core/store/cache.py`)

**Files:**
- Create: `social_scraper/core/store/cache.py`
- Test: `tests/component/test_store_cache.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for store.cache (30-day SQLite key/value)."""
from __future__ import annotations

import time

import pytest

from social_scraper.core.store.cache import LLMCache


pytestmark = pytest.mark.component


def test_put_then_get(tmp_path):
    cache = LLMCache(tmp_path / "c.sqlite")
    cache.put("k1", "value-one")
    assert cache.get("k1") == "value-one"
    cache.close()


def test_get_missing(tmp_path):
    cache = LLMCache(tmp_path / "c.sqlite")
    assert cache.get("nope") is None


def test_expired_entries_purged(tmp_path):
    cache = LLMCache(tmp_path / "c.sqlite", ttl_seconds=0)
    cache.put("k", "v")
    time.sleep(0.05)
    assert cache.get("k") is None


def test_key_helper_stable():
    k1 = LLMCache.make_key("post_id=abc", "model=q", "role=summarize")
    k2 = LLMCache.make_key("role=summarize", "post_id=abc", "model=q")
    assert k1 == k2  # sorted ⇒ order-independent
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/component/test_store_cache.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `social_scraper/core/store/cache.py`:

```python
"""30-day SQLite LLM-call cache."""
from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Optional


_DEFAULT_TTL_S = 30 * 24 * 3600


class LLMCache:
    def __init__(self, path: Path, ttl_seconds: int = _DEFAULT_TTL_S) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_seconds
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS llm_cache ("
            " key TEXT PRIMARY KEY, value TEXT NOT NULL, written_at REAL NOT NULL"
            ")"
        )
        self._conn.commit()

    @staticmethod
    def make_key(*parts: str) -> str:
        joined = "|".join(sorted(parts))
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[str]:
        now = time.time()
        cur = self._conn.execute(
            "SELECT value, written_at FROM llm_cache WHERE key = ?", (key,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        value, written_at = row
        if now - written_at > self.ttl:
            self._conn.execute("DELETE FROM llm_cache WHERE key = ?", (key,))
            self._conn.commit()
            return None
        return value

    def put(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO llm_cache (key, value, written_at) VALUES (?, ?, ?)",
            (key, value, time.time()),
        )
        self._conn.commit()

    def purge_expired(self) -> int:
        cutoff = time.time() - self.ttl
        cur = self._conn.execute("DELETE FROM llm_cache WHERE written_at < ?", (cutoff,))
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/component/test_store_cache.py -v`
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/store/cache.py tests/component/test_store_cache.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add LLMCache SQLite TTL store

Generic key/value with 30-day TTL (configurable). Used to cache LLM
summaries/rankings keyed by (item_id, model, role) via make_key.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Reputation port (`core/store/reputation.py`)

**Files:**
- Source: `dev-testing/claude/reddit_research/reputation.py`
- Source test: `dev-testing/claude/tests/test_render_and_reputation.py` (relevant sections)
- Create: `social_scraper/core/store/reputation.py`
- Test: `tests/component/test_store_reputation.py`

- [ ] **Step 1: Read the source file**

Open `dev-testing/claude/reddit_research/reputation.py` to understand the data shape (topic_areas → subs → score/promoted/last_seen).

- [ ] **Step 2: Write the failing test**

Create `tests/component/test_store_reputation.py`:

```python
"""Tests for reputation store (sub pinning per area)."""
from __future__ import annotations

import json

import pytest

from social_scraper.core.store.reputation import Reputation


pytestmark = pytest.mark.component


def test_load_missing_file_returns_empty(tmp_path):
    rep = Reputation(tmp_path / "rep.json")
    assert rep.load() == {"topic_areas": {}}


def test_promote_then_save(tmp_path):
    path = tmp_path / "rep.json"
    rep = Reputation(path)
    rep.load()
    rep.promote("ai_coding", "LocalLLaMA")
    rep.save()
    data = json.loads(path.read_text())
    assert data["topic_areas"]["ai_coding"]["subs"]["LocalLLaMA"]["promoted"] is True


def test_auto_update_records_score(tmp_path):
    rep = Reputation(tmp_path / "rep.json")
    rep.load()
    rep.auto_update("ai_coding", {"LocalLLaMA": {"signal_density": 0.42, "n_posts": 3}})
    rep.save()
    data = json.loads((tmp_path / "rep.json").read_text())
    s = data["topic_areas"]["ai_coding"]["subs"]["LocalLLaMA"]
    assert s["score"] == pytest.approx(0.42)
```

- [ ] **Step 3: Implement**

Create `social_scraper/core/store/reputation.py`:

```python
"""Per-topic-area subreddit reputation store (ported from dev-testing/claude)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Reputation:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._data: dict[str, Any] = {"topic_areas": {}}

    def load(self) -> dict:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
                self._data.setdefault("topic_areas", {})
            except json.JSONDecodeError:
                self._data = {"topic_areas": {}}
        return self._data

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2))

    def promote(self, area: str, sub: str) -> None:
        s = self._sub(area, sub)
        s["promoted"] = True

    def demote(self, area: str, sub: str) -> None:
        s = self._sub(area, sub)
        s["promoted"] = False

    def auto_update(self, area: str, sub_signals: dict[str, dict]) -> None:
        for sub, sig in sub_signals.items():
            s = self._sub(area, sub)
            s["score"] = float(sig.get("signal_density", 0.0))
            s["last_n_posts"] = int(sig.get("n_posts", 0))

    def _sub(self, area: str, sub: str) -> dict:
        areas = self._data.setdefault("topic_areas", {})
        area_data = areas.setdefault(area, {"subs": {}})
        return area_data.setdefault("subs", {}).setdefault(
            sub, {"promoted": False, "score": 0.0}
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/component/test_store_reputation.py -v`
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/store/reputation.py tests/component/test_store_reputation.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Port Reputation sub-pinning store from dev-testing/claude

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Reddit source port (`core/sources/reddit.py`)

**Files:**
- Source: `dev-testing/claude/reddit_research/fetch.py`
- Fixtures source: `dev-testing/claude/tests/fixtures/{comments_r_test.json, listing_r_test.json, subreddit_about.json, subreddit_search.json}`
- Create: `social_scraper/core/sources/reddit.py`
- Copy: 4 fixture files into `tests/component/fixtures/reddit/`
- Test: `tests/component/test_sources_reddit.py`

- [ ] **Step 1: Copy fixtures**

Run:
```powershell
New-Item -ItemType Directory -Force -Path 'tests\component\fixtures\reddit' | Out-Null
Copy-Item 'dev-testing\claude\tests\fixtures\*.json' 'tests\component\fixtures\reddit\' -Force
```

- [ ] **Step 2: Write the failing test**

Create `tests/component/test_sources_reddit.py`:

```python
"""Tests for RedditClient (ported)."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from social_scraper.core.schema import SourceKind
from social_scraper.core.sources.reddit import RedditClient


pytestmark = pytest.mark.component
FIX = Path(__file__).parent / "fixtures" / "reddit"


def _client_with(responses: dict[str, dict]) -> RedditClient:
    def handler(req: httpx.Request) -> httpx.Response:
        for key, payload in responses.items():
            if key in str(req.url):
                return httpx.Response(200, json=payload)
        return httpx.Response(404, json={})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return RedditClient(http, min_interval=0.0, jitter=0.0)


def test_search_subreddits_parses_fixture():
    data = json.loads((FIX / "subreddit_search.json").read_text())
    client = _client_with({"subreddits/search.json": data})
    results = client.search_subreddits("test", limit=5)
    assert isinstance(results, list)
    assert all("display_name" in r for r in results)


def test_about_subreddit_returns_data_or_none():
    data = json.loads((FIX / "subreddit_about.json").read_text())
    client = _client_with({"/about.json": data})
    out = client.about_subreddit("test")
    assert out is not None
    assert out.get("display_name") is not None


def test_fetch_listing_returns_rawposts():
    data = json.loads((FIX / "listing_r_test.json").read_text())
    client = _client_with({"top.json": data})
    posts, after = client.fetch_listing("test", listing="top", time_filter="month", limit=5)
    assert all(p.source == SourceKind.reddit for p in posts)
    assert all(p.subreddit for p in posts)


def test_fetch_comments_attaches_top_comments():
    data = json.loads((FIX / "comments_r_test.json").read_text())
    client = _client_with({"comments/": data})
    post = client.fetch_comments("test", "abc", limit=3)
    assert post.source == SourceKind.reddit
    assert isinstance(post.top_comments, list)
```

- [ ] **Step 3: Implement port**

Copy `dev-testing/claude/reddit_research/fetch.py` to `social_scraper/core/sources/reddit.py`, then apply these specific changes:

1. Change imports — replace `from reddit_research.schema import RawComment, RawPost` with `from social_scraper.core.schema import RawComment, RawPost, SourceKind`.
2. In `_parse_post`, set `source=SourceKind.reddit` on the returned `RawPost`.
3. Keep the `RedditBlockedError` class, the rate limiter, retry logic, and User-Agent handling unchanged.
4. Drop the module-level `DEFAULT_USER_AGENT` env-var fallback if duplicated; otherwise keep.

Verify the resulting file imports `SourceKind` and includes `source=SourceKind.reddit` in `_parse_post`'s return.

- [ ] **Step 4: Run tests**

Run: `pytest tests/component/test_sources_reddit.py -v`
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/sources/reddit.py tests/component/test_sources_reddit.py tests/component/fixtures/reddit/
git -C "P:\Documents\GIT\RedditScraper" commit -m "Port Reddit JSON-API client + fixtures from dev-testing/claude

RedditClient signatures unchanged. Adds source=SourceKind.reddit on every
parsed RawPost so multi-source aggregation works.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Google Trends source (`core/sources/google_trends.py`)

**Files:**
- Create: `social_scraper/core/sources/google_trends.py`
- Test: `tests/component/test_sources_google_trends.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for GoogleTrendsClient (TrendsPyG wrapper)."""
from __future__ import annotations

import pytest

from social_scraper.core.sources.google_trends import GoogleTrendsClient, TrendsResult


pytestmark = pytest.mark.component


class _FakeBackend:
    def __init__(self):
        self.calls = []

    def interest_over_time(self, kw_list, timeframe, geo):
        self.calls.append(("iot", kw_list, timeframe, geo))
        # Return shape similar to a DataFrame's to_dict("list").
        import datetime
        return {
            "dates": ["2026-04-12", "2026-04-13"],
            "values": {kw_list[0]: [50, 80]},
        }

    def related_queries(self, kw_list):
        self.calls.append(("rq", kw_list))
        return {kw_list[0]: {"top": ["q1", "q2", "q3"]}}


def test_interest_over_time_uses_backend():
    fake = _FakeBackend()
    client = GoogleTrendsClient(backend=fake)
    out: TrendsResult = client.snapshot("vibecoding", window_days=30, geo="")
    assert out.keyword == "vibecoding"
    assert out.geo == ""
    assert out.interest_over_time["values"]["vibecoding"] == [50, 80]
    assert out.top_related == ["q1", "q2", "q3"]
    assert fake.calls[0][0] == "iot"
    assert fake.calls[1][0] == "rq"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/component/test_sources_google_trends.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `social_scraper/core/sources/google_trends.py`:

```python
"""Google Trends source via trendspy (or pytrends fallback)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class _TrendsBackend(Protocol):
    def interest_over_time(self, kw_list: list[str], timeframe: str, geo: str) -> dict: ...
    def related_queries(self, kw_list: list[str]) -> dict: ...


def _window_to_timeframe(window_days: int) -> str:
    if window_days <= 7:
        return "now 7-d"
    if window_days <= 30:
        return "today 1-m"
    if window_days <= 90:
        return "today 3-m"
    return "today 12-m"


@dataclass
class TrendsResult:
    keyword: str
    geo: str
    window_days: int
    interest_over_time: dict
    top_related: list[str]


class _DefaultBackend:
    def __init__(self) -> None:
        try:
            import trendspy as _ts  # type: ignore[import-untyped]
            self._impl = _ts.Trends()
            self._kind = "trendspy"
        except ImportError:
            from pytrends.request import TrendReq  # type: ignore[import-untyped]
            self._impl = TrendReq(hl="en-US", tz=0)
            self._kind = "pytrends"

    def interest_over_time(self, kw_list, timeframe, geo):
        if self._kind == "pytrends":
            self._impl.build_payload(kw_list, timeframe=timeframe, geo=geo)
            df = self._impl.interest_over_time()
            if df is None or df.empty:
                return {"dates": [], "values": {kw_list[0]: []}}
            return {
                "dates": [str(d) for d in df.index.tolist()],
                "values": {kw_list[0]: df[kw_list[0]].tolist()},
            }
        # trendspy
        df = self._impl.interest_over_time(kw_list, timeframe=timeframe, geo=geo)
        if df is None or df.empty:
            return {"dates": [], "values": {kw_list[0]: []}}
        return {
            "dates": [str(d) for d in df.index.tolist()],
            "values": {kw_list[0]: df[kw_list[0]].tolist()},
        }

    def related_queries(self, kw_list):
        if self._kind == "pytrends":
            self._impl.build_payload(kw_list)
            rq = self._impl.related_queries()
            out = {}
            for kw in kw_list:
                entry = rq.get(kw, {})
                top_df = entry.get("top")
                out[kw] = {"top": top_df["query"].tolist() if top_df is not None else []}
            return out
        return self._impl.related_queries(kw_list)


class GoogleTrendsClient:
    def __init__(self, backend: _TrendsBackend | None = None) -> None:
        self._backend = backend or _DefaultBackend()

    def snapshot(self, keyword: str, window_days: int = 30, geo: str = "") -> TrendsResult:
        tf = _window_to_timeframe(window_days)
        iot = self._backend.interest_over_time([keyword], tf, geo)
        rq = self._backend.related_queries([keyword])
        top = rq.get(keyword, {}).get("top", []) if isinstance(rq, dict) else []
        return TrendsResult(
            keyword=keyword,
            geo=geo,
            window_days=window_days,
            interest_over_time=iot,
            top_related=list(top),
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/component/test_sources_google_trends.py -v`
Expected: 1 test passes.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/sources/google_trends.py tests/component/test_sources_google_trends.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add GoogleTrendsClient (trendspy primary, pytrends fallback)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: HN source (`core/sources/hn.py`)

**Files:**
- Create: `social_scraper/core/sources/hn.py`
- Test: `tests/component/test_sources_hn.py`
- Fixture: `tests/component/fixtures/hn/algolia_search.json`

- [ ] **Step 1: Create the fixture**

Create `tests/component/fixtures/hn/algolia_search.json` with this exact content:

```json
{
  "hits": [
    {
      "objectID": "1",
      "title": "Show HN: vibecoding tool",
      "url": "https://example.com/1",
      "author": "alice",
      "points": 42,
      "num_comments": 7,
      "created_at_i": 1700000000,
      "_tags": ["story"]
    },
    {
      "objectID": "c1",
      "story_id": "1",
      "comment_text": "Great tool!",
      "author": "bob",
      "points": 5,
      "created_at_i": 1700000100,
      "_tags": ["comment"]
    }
  ],
  "nbHits": 2
}
```

- [ ] **Step 2: Write the failing test**

```python
"""Tests for HNClient (Algolia search)."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from social_scraper.core.schema import SourceKind
from social_scraper.core.sources.hn import HNClient


pytestmark = pytest.mark.component
FIX = Path(__file__).parent / "fixtures" / "hn"


def test_search_parses_stories_and_comments():
    payload = json.loads((FIX / "algolia_search.json").read_text())

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = HNClient(http_client=http)
    posts = client.search("vibecoding", window_days=30, limit=20)
    assert len(posts) == 2
    assert {p.source for p in posts} == {SourceKind.hn}
    story = next(p for p in posts if "Show HN" in p.title)
    assert story.score == 42
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/component/test_sources_hn.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement**

Create `social_scraper/core/sources/hn.py`:

```python
"""Hacker News Algolia search client."""
from __future__ import annotations

import time
from typing import Optional

import httpx

from social_scraper.core.schema import RawPost, SourceKind


_ALGOLIA = "https://hn.algolia.com/api/v1/search"


class HNClient:
    def __init__(self, http_client: Optional[httpx.Client] = None, timeout: float = 30.0) -> None:
        self._http = http_client or httpx.Client(timeout=timeout)
        self._owns_http = http_client is None

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def search(self, query: str, window_days: int = 30, limit: int = 50) -> list[RawPost]:
        since_i = int(time.time()) - window_days * 86400
        params = {
            "query": query,
            "tags": "(story,comment)",
            "numericFilters": f"created_at_i>{since_i}",
            "hitsPerPage": min(limit, 100),
        }
        resp = self._http.get(_ALGOLIA, params=params)
        resp.raise_for_status()
        data = resp.json()
        out: list[RawPost] = []
        for hit in data.get("hits", []):
            tags = hit.get("_tags", [])
            if "story" in tags:
                out.append(self._story(hit))
            elif "comment" in tags:
                out.append(self._comment_as_post(hit))
        return out[:limit]

    def _story(self, h: dict) -> RawPost:
        oid = h.get("objectID", "")
        return RawPost(
            source=SourceKind.hn,
            id=f"story:{oid}",
            url=h.get("url") or f"https://news.ycombinator.com/item?id={oid}",
            title=h.get("title", ""),
            author=h.get("author"),
            body=h.get("story_text", "") or "",
            score=int(h.get("points") or 0),
            num_comments=int(h.get("num_comments") or 0),
            created_utc=float(h.get("created_at_i") or 0),
        )

    def _comment_as_post(self, h: dict) -> RawPost:
        oid = h.get("objectID", "")
        story_id = h.get("story_id", "")
        return RawPost(
            source=SourceKind.hn,
            id=f"comment:{oid}",
            url=f"https://news.ycombinator.com/item?id={oid}",
            title=(h.get("story_title") or "(comment)")[:120],
            author=h.get("author"),
            body=h.get("comment_text", "") or "",
            score=int(h.get("points") or 0),
            num_comments=0,
            created_utc=float(h.get("created_at_i") or 0),
            permalink=f"https://news.ycombinator.com/item?id={story_id}",
        )
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/component/test_sources_hn.py -v`
Expected: 1 test passes.

- [ ] **Step 6: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/sources/hn.py tests/component/test_sources_hn.py tests/component/fixtures/hn/
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add HNClient (Algolia search) + fixture

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: IndieHackers source (`core/sources/indiehackers.py`)

**Files:**
- Create: `social_scraper/core/sources/indiehackers.py`
- Test: `tests/component/test_sources_indiehackers.py`
- Fixture: `tests/component/fixtures/indiehackers/listing.html`

- [ ] **Step 1: Create the fixture**

Create `tests/component/fixtures/indiehackers/listing.html`:

```html
<!doctype html>
<html><body>
  <div class="feed-item">
    <div class="feed-item__content">
      <a href="/post/vibecoding-feels-different">Vibecoding feels different</a>
      <span class="feed-item__author">@alice</span>
      <span class="feed-item__upvotes">23</span>
    </div>
  </div>
  <div class="feed-item">
    <div class="feed-item__content">
      <a href="/post/another-thread">Another thread</a>
      <span class="feed-item__author">@bob</span>
      <span class="feed-item__upvotes">7</span>
    </div>
  </div>
</body></html>
```

- [ ] **Step 2: Write the failing test**

```python
"""Tests for IndieHackersClient (BeautifulSoup listing parse)."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from social_scraper.core.schema import SourceKind
from social_scraper.core.sources.indiehackers import IndieHackersClient


pytestmark = pytest.mark.component
FIX = Path(__file__).parent / "fixtures" / "indiehackers"


def test_fetch_listing_parses_two_items():
    html = (FIX / "listing.html").read_text()

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = IndieHackersClient(http_client=http, throttle_s=0.0)
    posts = client.fetch_listing("ideas-and-validation", limit=10)
    assert len(posts) == 2
    assert {p.source for p in posts} == {SourceKind.indiehackers}
    assert posts[0].title.startswith("Vibecoding")
    assert posts[0].score == 23
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/component/test_sources_indiehackers.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement**

Create `social_scraper/core/sources/indiehackers.py`:

```python
"""IndieHackers BeautifulSoup scraper."""
from __future__ import annotations

import time
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from social_scraper.core.schema import RawPost, SourceKind


_BASE = "https://www.indiehackers.com"


class IndieHackersClient:
    def __init__(
        self,
        http_client: Optional[httpx.Client] = None,
        throttle_s: float = 3.0,
        timeout: float = 30.0,
    ) -> None:
        self._http = http_client or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "social-scraper/0.2 (research)"},
        )
        self._owns_http = http_client is None
        self._throttle_s = throttle_s
        self._last_request_at = 0.0

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def _throttle(self) -> None:
        if self._throttle_s <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        wait = self._throttle_s - elapsed
        if wait > 0:
            time.sleep(wait)

    def fetch_listing(self, category: str, limit: int = 20) -> list[RawPost]:
        self._throttle()
        resp = self._http.get(f"{_BASE}/{category}")
        self._last_request_at = time.monotonic()
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        posts: list[RawPost] = []
        for item in soup.select(".feed-item")[:limit]:
            content = item.select_one(".feed-item__content")
            if not content:
                continue
            link = content.select_one("a")
            if not link:
                continue
            href = link.get("href", "")
            title = link.get_text(strip=True)
            author_el = content.select_one(".feed-item__author")
            author = author_el.get_text(strip=True).lstrip("@") if author_el else None
            score_el = content.select_one(".feed-item__upvotes")
            score = int(score_el.get_text(strip=True)) if score_el and score_el.get_text(strip=True).isdigit() else 0
            posts.append(RawPost(
                source=SourceKind.indiehackers,
                id=href.strip("/").split("/")[-1] or title[:40],
                url=f"{_BASE}{href}" if href.startswith("/") else href,
                title=title,
                author=author,
                score=score,
                num_comments=0,
                created_utc=0.0,
            ))
        return posts
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/component/test_sources_indiehackers.py -v`
Expected: 1 test passes.

- [ ] **Step 6: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/sources/indiehackers.py tests/component/test_sources_indiehackers.py tests/component/fixtures/indiehackers/
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add IndieHackersClient BeautifulSoup listing scraper

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Discover-subs pipeline step (`core/pipeline/discover_subs.py`)

This ports the topic-area + sub-discovery logic from dev-testing/claude/reddit_research/discover.py, but rebinds it to the new schema and OllamaClient.

**Files:**
- Source: `dev-testing/claude/reddit_research/discover.py`
- Create: `social_scraper/core/pipeline/discover_subs.py`
- Create: `social_scraper/core/pipeline/prompts.py` (lift relevant constants from dev-testing prompts.py)
- Test: `tests/component/test_pipeline_discover_subs.py`

- [ ] **Step 1: Lift prompt constants**

Read `dev-testing/claude/reddit_research/prompts.py` and copy `DISCOVER_SYSTEM` and `TOPIC_AREA_SYSTEM` into a new file `social_scraper/core/pipeline/prompts.py`. Leave other constants for later tasks to lift as needed.

- [ ] **Step 2: Write the failing test**

Create `tests/component/test_pipeline_discover_subs.py`:

```python
"""Tests for pipeline.discover_subs."""
from __future__ import annotations

import httpx
import pytest

from social_scraper.core.pipeline.discover_subs import discover_subreddits
from social_scraper.core.sources.reddit import RedditClient


pytestmark = pytest.mark.component


class _FakeLLM:
    def __init__(self, sub_names: list[str], area: str = "test_area") -> None:
        self._sub_names = sub_names
        self._area = area

    def json_call(self, system, user, model_cls):
        if "area" in model_cls.model_fields:
            return model_cls(area=self._area, new=True)
        return model_cls(subreddits=self._sub_names)


def _reddit_with_about_subs(approved: dict[str, dict]) -> RedditClient:
    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if "subreddits/search.json" in url:
            return httpx.Response(200, json={"data": {"children": []}})
        for name, data in approved.items():
            if f"/r/{name}/about.json" in url:
                return httpx.Response(200, json={"data": data})
        return httpx.Response(404, json={})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return RedditClient(http, min_interval=0.0, jitter=0.0)


def test_discover_filters_below_min_subs():
    llm = _FakeLLM(["BigSub", "TinySub"])
    reddit = _reddit_with_about_subs({
        "BigSub": {"display_name": "BigSub", "subscribers": 5000, "subreddit_type": "public", "over18": False},
        "TinySub": {"display_name": "TinySub", "subscribers": 100, "subreddit_type": "public", "over18": False},
    })
    subs, area = discover_subreddits(llm, reddit, "prompt", reputation={"topic_areas": {}}, max_subs=5)
    assert "BigSub" in subs
    assert "TinySub" not in subs
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/component/test_pipeline_discover_subs.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement**

Copy `dev-testing/claude/reddit_research/discover.py` to `social_scraper/core/pipeline/discover_subs.py`, then:

1. Replace imports:
   - `from reddit_research.fetch import RedditClient` → `from social_scraper.core.sources.reddit import RedditClient`
   - `from reddit_research.llm import LLM` → remove (use duck-typed `llm` parameter that has `json_call`)
   - `from reddit_research.prompts import DISCOVER_SYSTEM, TOPIC_AREA_SYSTEM` → `from social_scraper.core.pipeline.prompts import DISCOVER_SYSTEM, TOPIC_AREA_SYSTEM`
2. Rename top-level function `discover(...)` to `discover_subreddits(...)`. Keep the signature and body otherwise unchanged.
3. In the function, change `llm: LLM` annotation to `llm` (untyped — duck-typed for testability).

- [ ] **Step 5: Run tests**

Run: `pytest tests/component/test_pipeline_discover_subs.py -v`
Expected: 1 test passes.

- [ ] **Step 6: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/pipeline/discover_subs.py social_scraper/core/pipeline/prompts.py tests/component/test_pipeline_discover_subs.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Port sub-discovery pipeline step

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: Rank pipeline step (`core/pipeline/rank.py`) — REWRITE for strict JSON

This is the rewrite that addresses the G5 root cause. Use OllamaClient.json_call directly with a tight pydantic schema, and provide deterministic fallback per spec §10.

**Files:**
- Create: `social_scraper/core/pipeline/rank.py`
- Test: `tests/component/test_pipeline_rank.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for pipeline.rank with strict JSON + fallback."""
from __future__ import annotations

import pytest

from social_scraper.core.llm.ollama import OllamaError
from social_scraper.core.pipeline.rank import rank_posts
from social_scraper.core.schema import RawPost, SourceKind


pytestmark = pytest.mark.component


def _post(pid: str, score: int, comments: int = 0) -> RawPost:
    return RawPost(
        source=SourceKind.reddit, id=pid, url="u", title=pid,
        score=score, num_comments=comments, created_utc=1.0, subreddit="x",
    )


class _StubLLM:
    def __init__(self, ranked: dict[str, float] | None = None, raise_on_call: bool = False):
        self._ranked = ranked
        self._raise = raise_on_call

    def json_call(self, system, user, model_cls):
        if self._raise:
            raise OllamaError("forced")
        ranked_field = model_cls.model_fields["ranked"]
        item_cls = ranked_field.annotation.__args__[0]
        items = [item_cls(post_id=pid, relevance=rel) for pid, rel in self._ranked.items()]
        return model_cls(ranked=items)


def test_rank_orders_by_llm_then_native_score():
    posts = [_post("a", score=10), _post("b", score=100), _post("c", score=5)]
    llm = _StubLLM({"a": 0.9, "b": 0.1, "c": 0.9})
    ranked, used_fallback = rank_posts(llm, "prompt", posts, top_k=3)
    assert used_fallback is False
    # a and c both 0.9 → a (score 10) before c (score 5); b last.
    ids = [p.id for p, _ in ranked]
    assert ids == ["a", "c", "b"]


def test_rank_falls_back_on_ollama_error():
    posts = [_post("a", score=10, comments=5), _post("b", score=100, comments=1)]
    llm = _StubLLM(raise_on_call=True)
    ranked, used_fallback = rank_posts(llm, "prompt", posts, top_k=2)
    assert used_fallback is True
    # Fallback: sort by score + num_comments desc → b first.
    assert ranked[0][0].id == "b"


def test_rank_top_k_limits_output():
    posts = [_post(f"p{i}", score=i) for i in range(10)]
    llm = _StubLLM({f"p{i}": float(i) / 10 for i in range(10)})
    ranked, _ = rank_posts(llm, "prompt", posts, top_k=3)
    assert len(ranked) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/component/test_pipeline_rank.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `social_scraper/core/pipeline/rank.py`:

```python
"""LLM relevance ranker (strict-JSON Ollama mode + deterministic fallback)."""
from __future__ import annotations

import json

from pydantic import BaseModel

from social_scraper.core.llm.ollama import OllamaError
from social_scraper.core.schema import RawPost


_RANKER_SYSTEM = (
    "You are a relevance ranker. Given a research prompt and a list of post candidates, "
    "score each candidate's relevance to the prompt on a 0.0–1.0 scale."
)


class _RankItem(BaseModel):
    post_id: str
    relevance: float


class _RankedList(BaseModel):
    ranked: list[_RankItem]


def rank_posts(
    llm,
    prompt: str,
    posts: list[RawPost],
    top_k: int = 15,
) -> tuple[list[tuple[RawPost, float]], bool]:
    """Return (top_k_scored, used_fallback)."""
    if not posts:
        return [], False

    candidates = [
        {
            "post_id": p.id,
            "source": p.source.value,
            "title": p.title[:200],
            "body_snippet": p.body[:400],
            "score": p.score,
            "num_comments": p.num_comments,
        }
        for p in posts
    ]
    user = f"Prompt: {prompt}\n\nCandidates:\n{json.dumps(candidates)}"

    try:
        ranked = llm.json_call(_RANKER_SYSTEM, user, _RankedList)
        rel_map = {r.post_id: r.relevance for r in ranked.ranked}
        scored = [(p, rel_map.get(p.id, 0.0)) for p in posts]
        scored.sort(key=lambda t: (t[1], t[0].score, t[0].num_comments), reverse=True)
        return scored[:top_k], False
    except OllamaError:
        scored = [(p, 0.0) for p in posts]
        scored.sort(key=lambda t: (t[0].score + t[0].num_comments), reverse=True)
        return scored[:top_k], True
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/component/test_pipeline_rank.py -v`
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/pipeline/rank.py tests/component/test_pipeline_rank.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Rewrite rank.py around OllamaClient.json_call + deterministic fallback

Closes the G5 root cause. On OllamaError, falls back to score+comments
sort and signals via the used_fallback return flag so the pipeline can
record a warning in meta.json.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: Summarize pipeline step (`core/pipeline/summarize.py`)

**Files:**
- Create: `social_scraper/core/pipeline/summarize.py`
- Test: `tests/component/test_pipeline_summarize.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for pipeline.summarize."""
from __future__ import annotations

import pytest

from social_scraper.core.llm.ollama import OllamaError
from social_scraper.core.pipeline.summarize import summarize_post
from social_scraper.core.schema import PostSummary, RawComment, RawPost, SourceKind


pytestmark = pytest.mark.component


def _post() -> RawPost:
    return RawPost(
        source=SourceKind.reddit, id="abc", url="u", title="Hello",
        body="A useful long-ish body" * 5, score=10, num_comments=2,
        created_utc=1.0, subreddit="x",
        top_comments=[RawComment(id="c1", body="great", score=3, created_utc=2.0)],
    )


class _StubLLM:
    def __init__(self, fail: bool = False):
        self._fail = fail

    def json_call(self, system, user, model_cls):
        if self._fail:
            raise OllamaError("nope")
        return model_cls(
            post_id="abc",
            source=SourceKind.reddit,
            summary="A summary",
            themes=["t1"],
            relevance_to_prompt=0.5,
        )


def test_summarize_happy_path():
    summary, fallback = summarize_post(_StubLLM(), "prompt", _post(), relevance=0.5)
    assert isinstance(summary, PostSummary)
    assert summary.summary == "A summary"
    assert fallback is False


def test_summarize_fallback_on_llm_error():
    summary, fallback = summarize_post(_StubLLM(fail=True), "prompt", _post(), relevance=0.5)
    assert fallback is True
    assert summary.post_id == "abc"
    assert summary.summary  # extracted truncated text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/component/test_pipeline_summarize.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `social_scraper/core/pipeline/summarize.py`:

```python
"""Per-item summarization step."""
from __future__ import annotations

from social_scraper.core.llm.ollama import OllamaError
from social_scraper.core.schema import PostSummary, RawPost


_SUMMARIZE_SYSTEM = (
    "You summarize a single social-media post (+ top comments) in 3-5 sentences. "
    "Stay factual. Pull out themes (3-5 short tags). Score relevance 0.0–1.0 to the "
    "user's research prompt."
)


def summarize_post(
    llm,
    prompt: str,
    post: RawPost,
    relevance: float,
) -> tuple[PostSummary, bool]:
    """Return (PostSummary, used_fallback)."""
    comments_text = "\n".join(f"- ({c.score}) {c.body}" for c in post.top_comments[:5])
    user = (
        f"Research prompt: {prompt}\n\n"
        f"Source: {post.source.value}\n"
        f"Title: {post.title}\n\n"
        f"Body:\n{post.body[:2000]}\n\n"
        f"Top comments:\n{comments_text}"
    )
    try:
        result = llm.json_call(_SUMMARIZE_SYSTEM, user, PostSummary)
        # Ensure post_id/source match (LLM may have echoed them differently).
        result.post_id = post.id
        result.source = post.source
        return result, False
    except OllamaError:
        body_extract = (post.body or post.title)[:800]
        if post.top_comments:
            body_extract += f"\n\nTop comment: {post.top_comments[0].body[:300]}"
        return (
            PostSummary(
                post_id=post.id,
                source=post.source,
                summary=body_extract,
                themes=[],
                relevance_to_prompt=relevance,
            ),
            True,
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/component/test_pipeline_summarize.py -v`
Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/pipeline/summarize.py tests/component/test_pipeline_summarize.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add per-item summarize step with extract fallback

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: Narrate pipeline step (`core/pipeline/narrate.py`)

**Files:**
- Create: `social_scraper/core/pipeline/narrate.py`
- Test: `tests/component/test_pipeline_narrate.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for pipeline.narrate."""
from __future__ import annotations

import io

import pytest

from social_scraper.core.pipeline.narrate import narrate
from social_scraper.core.schema import PostSummary, SourceKind


pytestmark = pytest.mark.component


class _StubLLM:
    def __init__(self, text: str):
        self._text = text

    def chat_stream(self, system, user):
        for chunk in self._text.split(" "):
            yield chunk + " "


def test_narrate_writes_to_stream_and_returns_full():
    out = io.StringIO()
    llm = _StubLLM("Hello world narrative")
    summaries = [
        PostSummary(post_id="a", source=SourceKind.reddit, summary="s", themes=["t"], relevance_to_prompt=0.5),
    ]
    text = narrate(llm, "prompt", summaries, out_stream=out)
    assert "Hello" in text
    assert "Hello" in out.getvalue()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/component/test_pipeline_narrate.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `social_scraper/core/pipeline/narrate.py`:

```python
"""Cross-source narrative writer (streamed)."""
from __future__ import annotations

import json
from typing import TextIO

from social_scraper.core.schema import PostSummary


_NARRATE_SYSTEM = (
    "You are writing a research digest. Given a user prompt and a list of per-post "
    "summaries across multiple social sources, write 4–8 short paragraphs of factual "
    "narrative. Lead with the most salient finding. Cite source kind (Reddit, HN, "
    "IndieHackers, Google Trends) when claims come from one. Stay grounded — no "
    "speculation past what the summaries support."
)


def narrate(llm, prompt: str, summaries: list[PostSummary], out_stream: TextIO) -> str:
    payload = [
        {
            "post_id": s.post_id,
            "source": s.source.value,
            "summary": s.summary,
            "themes": s.themes,
            "relevance": s.relevance_to_prompt,
        }
        for s in summaries
    ]
    user = f"Prompt: {prompt}\n\nSummaries:\n{json.dumps(payload, indent=2)}"
    out_stream.write("# Digest\n\n")
    out_stream.flush()
    chunks: list[str] = []
    for chunk in llm.chat_stream(_NARRATE_SYSTEM, user):
        out_stream.write(chunk)
        out_stream.flush()
        chunks.append(chunk)
    out_stream.write("\n")
    return "# Digest\n\n" + "".join(chunks) + "\n"
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/component/test_pipeline_narrate.py -v`
Expected: 1 test passes.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/pipeline/narrate.py tests/component/test_pipeline_narrate.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add streamed narrate step

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 17: Ask pipeline orchestrator (`core/pipeline/ask.py`)

Orchestrates the full deterministic pipeline per spec §8. Tested as a workflow test against fakes.

**Files:**
- Create: `social_scraper/core/pipeline/ask.py`
- Test: `tests/workflow/test_pipeline_ask.py`

- [ ] **Step 1: Write the failing test**

```python
"""Workflow test for pipeline.ask — full pipeline against fakes."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from social_scraper.core.pipeline.ask import AskConfig, run_ask
from social_scraper.core.schema import (
    PostSummary,
    RawComment,
    RawPost,
    SourceKind,
)


pytestmark = pytest.mark.workflow


class _FakeLLM:
    """LLM that satisfies discover_subs, rank, summarize, and narrate contracts."""

    def __init__(self) -> None:
        self.model = "fake"

    def json_call(self, system, user, model_cls):
        name = model_cls.__name__
        if name == "_Proposal":
            return model_cls(subreddits=["test"])
        if name == "_TopicArea":
            return model_cls(area="test_area", new=True)
        if name == "_RankedList":
            item_cls = model_cls.model_fields["ranked"].annotation.__args__[0]
            return model_cls(ranked=[item_cls(post_id="abc", relevance=0.9)])
        if name == "PostSummary":
            return PostSummary(
                post_id="abc", source=SourceKind.reddit,
                summary="A summary.", themes=["t"], relevance_to_prompt=0.9,
            )
        raise AssertionError(f"unexpected schema {name}")

    def chat_stream(self, system, user):
        yield "The narrative."

    def ping(self):
        return True


class _FakeReddit:
    def about_subreddit(self, name):
        return {"display_name": name, "subscribers": 5000, "subreddit_type": "public", "over18": False}

    def search_subreddits(self, query, limit=10):
        return []

    def fetch_listing(self, sub, listing="top", time_filter="month", limit=25):
        post = RawPost(
            source=SourceKind.reddit, id="abc", url="u", title="t",
            body="b", score=10, num_comments=2, created_utc=1.0, subreddit="test",
        )
        return [post], None

    def fetch_comments(self, sub, post_id, limit=10):
        post = RawPost(
            source=SourceKind.reddit, id="abc", url="u", title="t",
            body="b", score=10, num_comments=2, created_utc=1.0, subreddit="test",
            top_comments=[RawComment(id="c1", body="great", score=2, created_utc=2.0)],
        )
        return post


class _FakeHN:
    def search(self, query, window_days=30, limit=50):
        return []


class _FakeIH:
    def fetch_listing(self, category, limit=20):
        return []


class _FakeTrends:
    def snapshot(self, keyword, window_days=30, geo=""):
        from social_scraper.core.sources.google_trends import TrendsResult
        return TrendsResult(
            keyword=keyword, geo=geo, window_days=window_days,
            interest_over_time={"dates": [], "values": {keyword: []}},
            top_related=[],
        )


def test_ask_writes_full_run_layout(tmp_path):
    cfg = AskConfig(
        topic="vibecoding",
        window_days=30,
        sources=[SourceKind.reddit, SourceKind.hn, SourceKind.indiehackers, SourceKind.google_trends],
        model="fake",
        summarizer="ollama",
        data_root=tmp_path / "data",
        cache_path=tmp_path / "cache" / "c.sqlite",
        reputation_path=tmp_path / "cache" / "rep.json",
    )
    result = run_ask(
        cfg,
        llm=_FakeLLM(),
        reddit=_FakeReddit(),
        hn=_FakeHN(),
        indiehackers=_FakeIH(),
        google_trends=_FakeTrends(),
        now=datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc),
    )
    run_dir: Path = result["run_dir"]
    assert run_dir.is_dir()
    assert (run_dir / "summary" / "summary.md").is_file()
    assert (run_dir / "raw" / "reddit.jsonl").is_file()
    assert (run_dir / "meta.json").is_file()
    timeline = tmp_path / "data" / "topics" / "vibecoding" / "timeline.md"
    assert timeline.is_file()
    assert "# vibecoding" in timeline.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/workflow/test_pipeline_ask.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `social_scraper/core/pipeline/ask.py`:

```python
"""Deterministic ask pipeline orchestrator (spec §8)."""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from social_scraper.core.llm.ollama import OllamaError
from social_scraper.core.pipeline.discover_subs import discover_subreddits
from social_scraper.core.pipeline.narrate import narrate
from social_scraper.core.pipeline.rank import rank_posts
from social_scraper.core.pipeline.summarize import summarize_post
from social_scraper.core.schema import PostSummary, RawPost, RunMeta, SourceKind
from social_scraper.core.store.cache import LLMCache
from social_scraper.core.store.reputation import Reputation
from social_scraper.core.store.run import RunWriter
from social_scraper.core.store.timeline import TimelineWriter


@dataclass
class AskConfig:
    topic: str
    window_days: int = 30
    sources: list[SourceKind] = field(default_factory=lambda: list(SourceKind))
    model: str = "qwen3-coder:30b"
    summarizer: str = "ollama"  # "ollama" | "claude"
    data_root: Path = Path("data")
    cache_path: Path = Path("cache/ollama_calls.sqlite")
    reputation_path: Path = Path("cache/reputation.json")
    listing: str = "top"
    time_filter: str = "month"
    limit: int = 25
    top_k: int = 15
    comments_per_post: int = 10
    min_comment_score: int = 5
    max_subs: int = 8


def _window_to_time_filter(window_days: int) -> str:
    if window_days <= 1:
        return "day"
    if window_days <= 7:
        return "week"
    if window_days <= 30:
        return "month"
    if window_days <= 365:
        return "year"
    return "all"


def run_ask(
    cfg: AskConfig,
    *,
    llm,
    reddit,
    hn,
    indiehackers,
    google_trends,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    writer = RunWriter(
        root=cfg.data_root,
        topic=cfg.topic,
        sources=cfg.sources,
        window_days=cfg.window_days,
        model=cfg.model,
        summarizer=cfg.summarizer,
        started=now,
    )
    cache = LLMCache(cfg.cache_path)
    rep = Reputation(cfg.reputation_path)
    rep.load()

    raw_posts: list[RawPost] = []

    # --- Reddit branch
    if SourceKind.reddit in cfg.sources:
        try:
            subs, area_slug = discover_subreddits(
                llm, reddit, cfg.topic, rep.load(), max_subs=cfg.max_subs,
            )
            tf = _window_to_time_filter(cfg.window_days)
            for sub in subs:
                try:
                    posts, _ = reddit.fetch_listing(
                        sub, listing=cfg.listing, time_filter=tf, limit=cfg.limit,
                    )
                    raw_posts.extend(posts)
                except Exception as exc:
                    writer.add_warning(f"reddit_listing_failed:{sub}:{exc}")
        except Exception as exc:
            writer.add_warning(f"reddit_branch_failed:{exc}")
            writer.mark_blocked(SourceKind.reddit)

    # --- HN branch
    if SourceKind.hn in cfg.sources:
        try:
            hn_posts = hn.search(cfg.topic, window_days=cfg.window_days, limit=50)
            raw_posts.extend(hn_posts)
        except Exception as exc:
            writer.add_warning(f"hn_failed:{exc}")
            writer.mark_blocked(SourceKind.hn)

    # --- IndieHackers branch (best-effort: fetch one category)
    if SourceKind.indiehackers in cfg.sources:
        try:
            ih_posts = indiehackers.fetch_listing("ideas-and-validation", limit=20)
            raw_posts.extend(ih_posts)
        except Exception as exc:
            writer.add_warning(f"ih_failed:{exc}")
            writer.mark_blocked(SourceKind.indiehackers)

    # --- Trends branch (stored as a blob, not a "post")
    if SourceKind.google_trends in cfg.sources:
        try:
            trends = google_trends.snapshot(cfg.topic, window_days=cfg.window_days)
            writer.write_raw_blob(SourceKind.google_trends, {
                "keyword": trends.keyword,
                "window_days": trends.window_days,
                "interest_over_time": trends.interest_over_time,
                "top_related": trends.top_related,
            })
        except Exception as exc:
            writer.add_warning(f"trends_failed:{exc}")
            writer.mark_blocked(SourceKind.google_trends)

    if not raw_posts and SourceKind.google_trends not in writer.meta.sources:
        writer.add_warning("no_data_collected")
        writer.write_summary_md(
            f"# {cfg.topic}\n\nNo data collected — try a wider window or different sources.\n"
        )
        writer.finalize(finished=datetime.now(timezone.utc))
        cache.close()
        return {"run_dir": writer.run_dir, "summary_path": writer.run_dir / "summary" / "summary.md"}

    # Group + write raw
    for source in {p.source for p in raw_posts}:
        writer.write_raw(source, [p for p in raw_posts if p.source == source])

    # Rank
    ranked, used_rank_fallback = rank_posts(llm, cfg.topic, raw_posts, top_k=cfg.top_k)
    if used_rank_fallback:
        writer.add_warning("rank_fallback_used")
    writer.write_ranked([
        {"post_id": p.id, "source": p.source.value, "relevance": rel}
        for p, rel in ranked
    ])

    # Fetch deep + summarize per top item
    summaries: list[PostSummary] = []
    for post, relevance in ranked:
        full_post = post
        if post.source == SourceKind.reddit and post.subreddit:
            try:
                full_post = reddit.fetch_comments(
                    post.subreddit, post.id, limit=cfg.comments_per_post,
                )
            except Exception as exc:
                writer.add_warning(f"reddit_comments_failed:{post.id}:{exc}")

        cache_key = LLMCache.make_key(
            f"item_id={full_post.id}",
            f"model={cfg.model}",
            f"role=summarize",
        )
        cached = cache.get(cache_key)
        if cached is not None:
            try:
                summary = PostSummary.model_validate_json(cached)
                summary.relevance_to_prompt = relevance
                summaries.append(summary)
                continue
            except Exception:
                pass

        summary, fallback = summarize_post(llm, cfg.topic, full_post, relevance=relevance)
        if fallback:
            writer.add_warning(f"summarize_fallback:{full_post.id}")
        summaries.append(summary)
        cache.put(cache_key, summary.model_dump_json())

    # Narrate (streamed to stdout AND captured for the file)
    buf = io.StringIO()
    narrative = narrate(llm, cfg.topic, summaries, out_stream=buf)
    writer.write_summary_md(narrative)

    # Timeline append
    first_para = narrative.split("\n\n")[1] if "\n\n" in narrative else narrative[:300]
    TimelineWriter(cfg.data_root, writer.slug).append(
        when=now, run_dir=writer.run_dir, verdict=first_para,
    )

    finished = datetime.now(timezone.utc)
    writer.finalize(finished=finished)
    cache.close()

    return {
        "run_dir": writer.run_dir,
        "summary_path": writer.run_dir / "summary" / "summary.md",
        "narrative_preview": first_para,
        "warnings": list(writer.meta.warnings),
    }
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/workflow/test_pipeline_ask.py -v`
Expected: 1 test passes.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/pipeline/ask.py tests/workflow/test_pipeline_ask.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add deterministic ask pipeline orchestrator (spec §8)

Discover → fetch (parallelizable later) → rank → fetch_deep → summarize
→ narrate → write run folder + timeline. Per-source failures are
contained: branch failures append a warning and mark blocked, the rest
of the pipeline continues.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 18: Discover agentic loop (`core/agent/discover.py`)

Uses smolagents.CodeAgent with the four scraper tools + a `fetch_topic` tool that calls `run_ask`. Hard caps per spec §9.

**Files:**
- Create: `social_scraper/core/agent/discover.py`
- Test: `tests/component/test_agent_discover.py` (tool functions)
- Test: `tests/workflow/test_agent_discover_loop.py` (full loop with stub driver)

- [ ] **Step 1: Write the component-level tool tests**

```python
"""Tests for individual agent tool functions."""
from __future__ import annotations

import pytest

from social_scraper.core.agent.discover import (
    _tool_top_trending_hn,
    _tool_top_trending_reddit,
)


pytestmark = pytest.mark.component


class _FakeReddit:
    def fetch_listing(self, sub, listing, time_filter, limit):
        from social_scraper.core.schema import RawPost, SourceKind
        posts = [
            RawPost(source=SourceKind.reddit, id=f"r{i}", url="u",
                    title=f"Trending topic {i}", score=100 - i, num_comments=10,
                    created_utc=1.0, subreddit="popular")
            for i in range(3)
        ]
        return posts, None


class _FakeHN:
    def search(self, query, window_days, limit):
        from social_scraper.core.schema import RawPost, SourceKind
        return [
            RawPost(source=SourceKind.hn, id=f"h{i}", url="u",
                    title=f"HN trend {i}", score=50 - i, num_comments=5,
                    created_utc=1.0)
            for i in range(3)
        ]


def test_top_trending_reddit_returns_titles():
    out = _tool_top_trending_reddit(_FakeReddit(), window_days=7, limit=2)
    assert len(out) == 2
    assert all(isinstance(t, str) for t in out)
    assert "Trending topic" in out[0]


def test_top_trending_hn_returns_titles():
    out = _tool_top_trending_hn(_FakeHN(), window_days=7, limit=2)
    assert len(out) == 2
    assert "HN trend" in out[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/component/test_agent_discover.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `social_scraper/core/agent/discover.py`:

```python
"""Agentic discover loop using smolagents.CodeAgent.

The loop has hard caps (5 iterations, 90s wall clock per iteration) per spec §9.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from social_scraper.core.pipeline.ask import AskConfig, run_ask
from social_scraper.core.schema import SourceKind


# --- Tool implementations (plain functions; agent will wrap these) -----------

def _tool_top_trending_reddit(reddit, window_days: int, limit: int) -> list[str]:
    """Return top-N titles from r/popular over the window."""
    if window_days <= 1:
        tf = "day"
    elif window_days <= 7:
        tf = "week"
    else:
        tf = "month"
    posts, _ = reddit.fetch_listing("popular", listing="top", time_filter=tf, limit=limit)
    return [p.title for p in posts[:limit]]


def _tool_top_trending_hn(hn, window_days: int, limit: int) -> list[str]:
    """Return top story titles from HN over the window (top stories of last N days)."""
    posts = hn.search("", window_days=window_days, limit=limit * 2)
    stories = [p for p in posts if p.id.startswith("story:")]
    stories.sort(key=lambda p: p.score, reverse=True)
    return [p.title for p in stories[:limit]]


def _tool_top_trending_google(trends_backend, window_days: int, limit: int) -> list[str]:
    """Best-effort trending keywords. trendspy exposes `trending_now`; pytrends does not.
    Returns [] if backend can't supply.
    """
    impl = getattr(trends_backend, "_impl", None)
    if impl is None:
        return []
    fn = getattr(impl, "trending_now", None)
    if fn is None:
        return []
    try:
        items = fn(geo="US")
        return [getattr(x, "keyword", str(x)) for x in list(items)[:limit]]
    except Exception:
        return []


# --- Agent loop --------------------------------------------------------------

@dataclass
class DiscoverConfig:
    window_days: int = 30
    top_n: int = 5
    sources: list[SourceKind] = field(default_factory=lambda: list(SourceKind))
    model: str = "qwen3-coder:30b"
    summarizer: str = "ollama"
    data_root: Path = Path("data")
    cache_path: Path = Path("cache/ollama_calls.sqlite")
    reputation_path: Path = Path("cache/reputation.json")
    max_iterations: int = 5
    per_iter_timeout_s: int = 90


def run_discover(
    cfg: DiscoverConfig,
    *,
    agent_driver,        # something with .pick_topics(candidates: list[str], top_n: int) -> list[str]
    llm,                 # passed through to run_ask
    reddit,
    hn,
    indiehackers,
    google_trends,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    parent_dir = cfg.data_root / "runs" / f"discover_{now.strftime('%Y-%m-%dT%H-%M-%SZ')}"
    parent_dir.mkdir(parents=True, exist_ok=True)
    (parent_dir / "summary").mkdir(exist_ok=True)

    candidates: list[str] = []
    started = time.monotonic()
    iters = 0
    partial = False

    if SourceKind.reddit in cfg.sources:
        if time.monotonic() - started > cfg.per_iter_timeout_s * cfg.max_iterations:
            partial = True
        else:
            try:
                candidates.extend(_tool_top_trending_reddit(reddit, cfg.window_days, cfg.top_n * 2))
            except Exception:
                pass
            iters += 1
    if SourceKind.hn in cfg.sources and iters < cfg.max_iterations:
        try:
            candidates.extend(_tool_top_trending_hn(hn, cfg.window_days, cfg.top_n * 2))
        except Exception:
            pass
        iters += 1
    if SourceKind.google_trends in cfg.sources and iters < cfg.max_iterations:
        try:
            backend = getattr(google_trends, "_backend", None)
            if backend is not None:
                candidates.extend(_tool_top_trending_google(backend, cfg.window_days, cfg.top_n * 2))
        except Exception:
            pass
        iters += 1

    if not candidates:
        (parent_dir / "summary" / "summary.md").write_text(
            "# discover run\n\nNo trending candidates available — sources returned empty.\n"
        )
        return {"run_dir": parent_dir, "summary_path": parent_dir / "summary" / "summary.md", "partial": True}

    # Dedup + cap
    seen = set()
    deduped: list[str] = []
    for c in candidates:
        cl = c.strip().lower()
        if cl and cl not in seen:
            seen.add(cl)
            deduped.append(c.strip())

    picked = agent_driver.pick_topics(deduped, top_n=cfg.top_n)

    child_summaries: list[tuple[str, Path]] = []
    for topic in picked:
        if iters >= cfg.max_iterations or (time.monotonic() - started) > cfg.per_iter_timeout_s * cfg.max_iterations:
            partial = True
            break
        ask_cfg = AskConfig(
            topic=topic,
            window_days=cfg.window_days,
            sources=cfg.sources,
            model=cfg.model,
            summarizer=cfg.summarizer,
            data_root=cfg.data_root,
            cache_path=cfg.cache_path,
            reputation_path=cfg.reputation_path,
        )
        result = run_ask(
            ask_cfg,
            llm=llm, reddit=reddit, hn=hn,
            indiehackers=indiehackers, google_trends=google_trends,
            now=datetime.now(timezone.utc),
        )
        child_summaries.append((topic, result["summary_path"]))
        iters += 1

    md_lines = [f"# discover run — {now.strftime('%Y-%m-%dT%H:%M:%SZ')}\n"]
    if partial:
        md_lines.append("> ⚠ discover_partial — cap hit before all picks completed\n")
    md_lines.append("\n## Candidate trends considered\n")
    for c in deduped:
        md_lines.append(f"- {c}")
    md_lines.append("\n## Picked & analyzed\n")
    for topic, path in child_summaries:
        rel = path.relative_to(parent_dir.parent.parent) if cfg.data_root in path.parents else path
        md_lines.append(f"### {topic}")
        md_lines.append(f"[summary]({rel})\n")
    (parent_dir / "summary" / "summary.md").write_text("\n".join(md_lines) + "\n")

    return {
        "run_dir": parent_dir,
        "summary_path": parent_dir / "summary" / "summary.md",
        "partial": partial,
        "child_count": len(child_summaries),
    }
```

Note: the actual smolagents integration is deferred — this v1 loop uses a duck-typed `agent_driver` so we can swap a real `smolagents.CodeAgent` in via a thin adapter later without touching `run_discover`. The CLI/MCP layer creates the adapter. This makes the loop testable and keeps the agent failure modes from polluting the deterministic core.

- [ ] **Step 4: Run tests**

Run: `pytest tests/component/test_agent_discover.py -v`
Expected: 2 tests pass.

- [ ] **Step 5: Write the workflow-level test**

Create `tests/workflow/test_agent_discover_loop.py`:

```python
"""Workflow test for full discover loop."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from social_scraper.core.agent.discover import DiscoverConfig, run_discover
from social_scraper.core.schema import SourceKind


pytestmark = pytest.mark.workflow


# Reuse the fakes from test_pipeline_ask via copy (kept self-contained per skill).

class _FakeLLM:
    model = "fake"
    def json_call(self, system, user, model_cls):
        name = model_cls.__name__
        if name == "_Proposal":
            return model_cls(subreddits=["test"])
        if name == "_TopicArea":
            return model_cls(area="test_area", new=True)
        if name == "_RankedList":
            item_cls = model_cls.model_fields["ranked"].annotation.__args__[0]
            return model_cls(ranked=[item_cls(post_id="r0", relevance=0.7)])
        if name == "PostSummary":
            from social_scraper.core.schema import PostSummary
            return PostSummary(
                post_id="r0", source=SourceKind.reddit, summary="s",
                themes=["t"], relevance_to_prompt=0.7,
            )
        raise AssertionError(name)
    def chat_stream(self, system, user):
        yield "Narrative."
    def ping(self):
        return True


class _FakeReddit:
    def about_subreddit(self, name):
        return {"display_name": name, "subscribers": 5000, "subreddit_type": "public", "over18": False}
    def search_subreddits(self, q, limit=10):
        return []
    def fetch_listing(self, sub, listing="top", time_filter="month", limit=25):
        from social_scraper.core.schema import RawPost
        return [
            RawPost(source=SourceKind.reddit, id=f"r{i}", url="u", title=f"Trend {i}",
                    score=10 - i, num_comments=2, created_utc=1.0, subreddit=sub)
            for i in range(3)
        ], None
    def fetch_comments(self, sub, post_id, limit=10):
        from social_scraper.core.schema import RawPost
        return RawPost(source=SourceKind.reddit, id=post_id, url="u", title="t",
                       score=10, num_comments=2, created_utc=1.0, subreddit=sub)


class _FakeHN:
    def search(self, q, window_days=30, limit=50):
        return []


class _FakeIH:
    def fetch_listing(self, category, limit=20):
        return []


class _FakeTrends:
    _backend = None
    def snapshot(self, kw, window_days=30, geo=""):
        from social_scraper.core.sources.google_trends import TrendsResult
        return TrendsResult(keyword=kw, geo=geo, window_days=window_days,
                            interest_over_time={"dates": [], "values": {kw: []}},
                            top_related=[])


class _PickFirst:
    """Stand-in for the agent driver — picks the first N candidates."""
    def pick_topics(self, candidates, top_n):
        return candidates[:top_n]


def test_discover_writes_parent_run_with_children(tmp_path):
    cfg = DiscoverConfig(
        window_days=7, top_n=2,
        sources=[SourceKind.reddit, SourceKind.hn, SourceKind.indiehackers, SourceKind.google_trends],
        data_root=tmp_path / "data",
        cache_path=tmp_path / "cache" / "c.sqlite",
        reputation_path=tmp_path / "cache" / "rep.json",
    )
    result = run_discover(
        cfg, agent_driver=_PickFirst(),
        llm=_FakeLLM(), reddit=_FakeReddit(), hn=_FakeHN(),
        indiehackers=_FakeIH(), google_trends=_FakeTrends(),
        now=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )
    assert result["partial"] is False
    assert result["child_count"] == 2
    assert result["summary_path"].is_file()
```

- [ ] **Step 6: Run workflow test**

Run: `pytest tests/workflow/test_agent_discover_loop.py -v`
Expected: 1 test passes.

- [ ] **Step 7: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/core/agent/discover.py tests/component/test_agent_discover.py tests/workflow/test_agent_discover_loop.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add agentic discover loop with 5-iter / 90s caps

Uses a duck-typed agent_driver so tests can stub the pick. CLI/MCP
layer wraps a real smolagents.CodeAgent. Per-iter exception isolation
keeps one bad source from killing the whole loop.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 19: CLI (`social_scraper/cli.py`)

**Files:**
- Create: `social_scraper/cli.py`
- Test: `tests/workflow/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the scrape CLI."""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner


pytestmark = pytest.mark.workflow


def test_cli_help():
    from social_scraper.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "ask" in result.stdout
    assert "discover" in result.stdout


def test_cli_timeline_missing_topic(tmp_path):
    from social_scraper.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["timeline", "nonexistent", "--data-root", str(tmp_path)])
    assert result.exit_code != 0
    assert "no timeline" in result.stdout.lower() or "no timeline" in result.stderr.lower()


def test_cli_timeline_existing(tmp_path):
    topic_dir = tmp_path / "topics" / "x"
    topic_dir.mkdir(parents=True)
    (topic_dir / "timeline.md").write_text("# x\n\n## 2026-05-11\n\nverdict\n")
    from social_scraper.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["timeline", "x", "--data-root", str(tmp_path)])
    assert result.exit_code == 0
    assert "verdict" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/workflow/test_cli.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `social_scraper/cli.py`:

```python
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

    cfg = AskConfig(
        topic=topic,
        window_days=window_days,
        sources=_parse_sources(sources),
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
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/workflow/test_cli.py -v`
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/cli.py tests/workflow/test_cli.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add scrape CLI (ask/discover/timeline/list)

Ollama-driven entry point; pings before running. Uses inline
_OllamaPickDriver as the agent driver for discover.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 20: MCP server (`social_scraper/mcp_server.py`)

**Files:**
- Create: `social_scraper/mcp_server.py`
- Test: `tests/workflow/test_mcp_server.py`

- [ ] **Step 1: Write the failing test**

```python
"""In-process tests for the MCP server tools.

These call the *implementations* directly (not via the MCP transport) to verify
the return-shape contract — paths only on ask/discover, content only on
read_summary/read_timeline.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from social_scraper.mcp_server import (
    _impl_ask,
    _impl_discover,
    _impl_read_summary,
    _impl_read_timeline,
)


pytestmark = pytest.mark.workflow


def test_read_summary_returns_content(tmp_path):
    rd = tmp_path / "run1"
    (rd / "summary").mkdir(parents=True)
    (rd / "summary" / "summary.md").write_text("# hello\n")
    out = _impl_read_summary(str(rd))
    assert out["content"].startswith("# hello")


def test_read_timeline_returns_content(tmp_path):
    (tmp_path / "topics" / "x").mkdir(parents=True)
    (tmp_path / "topics" / "x" / "timeline.md").write_text("# x\n")
    out = _impl_read_timeline("x", data_root=str(tmp_path))
    assert out["content"].startswith("# x")


def test_read_summary_missing_returns_error(tmp_path):
    out = _impl_read_summary(str(tmp_path / "nope"))
    assert "error" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/workflow/test_mcp_server.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `social_scraper/mcp_server.py`:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/workflow/test_mcp_server.py -v`
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add social_scraper/mcp_server.py tests/workflow/test_mcp_server.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add MCP server with 4 tools (ask, discover, read_summary, read_timeline)

ask/discover return only paths for token efficiency; content read is
an explicit opt-in. Falls back gracefully if Ollama is unreachable.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 21: 3x-clean component + workflow gate

**Files:** none (validation only)

- [ ] **Step 1: Run all component tests three times consecutively**

Run:
```powershell
pytest tests/component/ -m component --count=3 -v
```

Expected: every test passes 3 times, exit code 0. If any test fails or is flaky, STOP and write a status note to `docs/superpowers/plans/STATUS.md` with the failing test name and traceback. Do not proceed.

- [ ] **Step 2: Run all workflow tests three times consecutively**

Run:
```powershell
pytest tests/workflow/ -m workflow --count=3 -v
```

Expected: every test passes 3 times, exit code 0. Same rule on failure.

- [ ] **Step 3: Combined run (sanity)**

Run:
```powershell
pytest -m "component or workflow" --count=3
```

Expected: green.

- [ ] **Step 4: Commit a marker tag (no code change)**

```powershell
git -C "P:\Documents\GIT\RedditScraper" tag -a v0.2.0-rc1 -m "Component + workflow tests 3x clean"
```

(Tag only — no commit needed. If the tag command fails because the tag exists, increment to `-rc2`.)

---

## Task 22: E2E test against real services

**Files:**
- Create: `tests/e2e/test_real_ask.py`

- [ ] **Step 1: Verify Ollama and the model are available**

Run:
```powershell
curl http://localhost:11434/api/tags
```

Expected: HTTP 200, JSON listing models. If `qwen3-coder:30b` is not in the list:
```powershell
ollama pull qwen3-coder:30b
```

If Ollama is not running, start it (manual operator step) and write to STATUS.md that you waited. Do not proceed without the model loaded.

- [ ] **Step 2: Write the e2e test**

Create `tests/e2e/test_real_ask.py`:

```python
"""End-to-end test against real Ollama + real Reddit/HN/IH/Trends.

Run with: pytest tests/e2e --e2e -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from social_scraper.core.llm.ollama import OllamaClient
from social_scraper.core.pipeline.ask import AskConfig, run_ask
from social_scraper.core.schema import SourceKind
from social_scraper.core.sources.google_trends import GoogleTrendsClient
from social_scraper.core.sources.hn import HNClient
from social_scraper.core.sources.indiehackers import IndieHackersClient
from social_scraper.core.sources.reddit import RedditClient, make_client


pytestmark = pytest.mark.e2e


def test_known_good_topic(tmp_path):
    llm = OllamaClient(model="qwen3-coder:30b")
    assert llm.ping(), "Ollama unreachable — start `ollama serve` and pull qwen3-coder:30b"

    cfg = AskConfig(
        topic="local LLM coding",
        window_days=7,
        sources=[SourceKind.reddit, SourceKind.hn, SourceKind.indiehackers, SourceKind.google_trends],
        model="qwen3-coder:30b",
        summarizer="ollama",
        data_root=tmp_path / "data",
        cache_path=tmp_path / "cache" / "c.sqlite",
        reputation_path=tmp_path / "cache" / "rep.json",
        top_k=5,
    )
    result = run_ask(
        cfg,
        llm=llm,
        reddit=RedditClient(make_client()),
        hn=HNClient(),
        indiehackers=IndieHackersClient(),
        google_trends=GoogleTrendsClient(),
    )
    summary_path: Path = result["summary_path"]
    text = summary_path.read_text(encoding="utf-8")
    assert len(text) > 200, f"summary too short ({len(text)} chars)"

    meta_path = result["run_dir"] / "meta.json"
    import json
    meta = json.loads(meta_path.read_text())
    # We can tolerate some warnings (e.g. trends_failed) but rank_fallback_used is a regression.
    assert "rank_fallback_used" not in meta["warnings"], f"rank fell back: {meta['warnings']}"
```

- [ ] **Step 3: Run once**

Run:
```powershell
pytest tests/e2e --e2e -v
```

Expected: pass. If it fails on `rank_fallback_used`, that's the v1 G5-style regression — STOP and write a STATUS.md note with the run_dir path and meta.json contents.

- [ ] **Step 4: Run 3x consecutively (the 3x gate)**

Run:
```powershell
pytest tests/e2e --e2e --count=3 -v
```

Expected: 3 consecutive passes. If any run fails, STOP and write STATUS.md.

- [ ] **Step 5: Commit**

```powershell
git -C "P:\Documents\GIT\RedditScraper" add tests/e2e/test_real_ask.py
git -C "P:\Documents\GIT\RedditScraper" commit -m "Add e2e test against real Ollama + Reddit/HN/IH/Trends

Single known-good topic (\"local LLM coding\", 7-day window). Asserts
summary is non-trivial and that rank_fallback_used is NOT in warnings.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Tag v0.2.0**

```powershell
git -C "P:\Documents\GIT\RedditScraper" tag -a v0.2.0 -m "v2 social scraper — component + workflow + e2e all 3x clean"
```

---

## Status note path

If at any point a task cannot be completed (test won't pass, dependency missing, API broken), create or append to `docs/superpowers/plans/STATUS.md` with:

```markdown
## YYYY-MM-DD HH:MM:SSZ — Task N blocked

**What I was doing:** [one sentence]
**What failed:** [error message or behavior]
**What I tried:** [bulleted]
**What I need from you:** [one sentence]
```

Then stop. Do not skip the task or "best-effort" past a real failure.

---

## Self-review

**Spec coverage:** Every numbered section of the spec maps to at least one task:
- §3 (operating model) → Tasks 19, 20
- §4 (CLI surface) → Task 19
- §5 (MCP tools) → Task 20
- §6 (package layout) → Task 1, then individual file tasks
- §7 (on-disk layout) → Task 5 (RunWriter), Task 6 (TimelineWriter)
- §8 (ask pipeline) → Task 17, with sub-steps in 13/14/15/16
- §9 (discover loop) → Task 18
- §10 (LLM JSON contract + repair) → Task 3, used in Tasks 14/15
- §11 (error handling) → covered in Tasks 14/15/17/18 with explicit fallback tests
- §12 (config & secrets) → Task 1 (env vars), Task 3 (OLLAMA_BASE_URL), Task 4 (claude binary)
- §13 (testing) → Task 21 (component/workflow 3x), Task 22 (e2e 3x)
- §14 (deps) → Task 1 pyproject.toml
- §15 (migration plan) → Tasks 8/9/13 ports, Task 14 rewrite
- §16 (out of scope) → respected throughout (no X/Twitter, no YouTube, no Selenium)

**Placeholder scan:** No TBD / TODO / "implement later" in any step. All code blocks are complete.

**Type consistency:** `RawPost.source` (SourceKind) used consistently across all source modules. `AskConfig` / `DiscoverConfig` parameter names match between definition (Tasks 17, 18) and call sites (Tasks 19, 20). MCP return shape `{run_dir, summary_path, one_line_status}` consistent across Task 20 contract and Task 17/18 return.

**Known gaps acknowledged:**
- The Google Trends `trending_now` API is best-effort — Task 18 returns `[]` if the backend doesn't expose it. Document, don't fail.
- IndieHackers selectors are speculative (per ProductResearch STATE.md §2). The fixture-based test in Task 12 will pass; the e2e test in Task 22 may need selector adjustment if the site has changed. If so, the failure shows up in the `ih_failed:...` warning rather than killing the run.
