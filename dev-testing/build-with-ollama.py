"""
Drop-in replacement for the aider non-interactive recipe.

Reads a spec file, asks a local Ollama model to emit every target file in
aider's whole-file edit format (path on its own line, then a fenced code
block), parses those blocks, and writes them to disk relative to the git
root.

We need this because aider's own runner hangs indefinitely on the Ollama
stream on Windows when stdin is closed (the prompt_toolkit "No Windows
console found" path). Ollama itself works fine - we just bypass aider.

Why this script instead of aider:
  - Aider hangs on /api/chat streaming with closed stdin on Windows.
  - We don't need aider's diff/edit logic - the model emits whole files.
  - We control retries, validation, and exit codes directly.

Usage:
  python build-with-ollama.py \\
    --spec build-prompt.md \\
    --target aider/pyproject.toml \\
    --target aider/reddit_scraper/cli.py \\
    --model qwen3-coder:30b \\
    --root P:/Documents/GIT/RedditScraper

Exit codes:
  0  every target was written non-empty
  2  Ollama unreachable or returned an error
  3  model response did not contain a block for one or more targets
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


OLLAMA_URL = "http://localhost:11434/api/chat"


def build_messages(spec_text: str, targets: list[str], root_prefix: str) -> list[dict]:
    target_list = "\n".join(f"   - {t}" for t in targets)
    example_path = targets[0] if targets else f"{root_prefix}/example.py"
    user_msg = f"""The reference spec is included below in full. Execute it in this single response. You will not get another turn.

CRITICAL RULES:
1. Emit EVERY file listed in REQUIRED FILES below in this one response. Do not pause, do not stop after one file, do not ask for confirmation.
2. Every file path you emit must be exactly one of the REQUIRED FILES entries (the path relative to the git root).
3. Format: the file path on its own line, immediately followed by a fenced code block. Inside the fence: only file content. Nothing between the path and the opening fence except a single newline.
4. Do NOT write commentary, headings, or prose between files. Just file blocks back-to-back.
5. The closing fence for one file must be followed by a blank line and then the next file's path.

REQUIRED FILES (this exact order):
{target_list}

FORMAT EXAMPLE (your entire response must look like this - just file blocks):

{example_path}
```python
# full content of {example_path}
```

(continue with every remaining required file in the same format)

===== BEGIN SPEC =====
{spec_text}
===== END SPEC =====

Begin now. Output only file blocks, in the required order.
"""
    return [
        {
            "role": "system",
            "content": (
                "You are a code generator. Output ONLY whole-file blocks in the "
                "format requested. No prose between blocks. No commentary. "
                "Every file path you write must match one of the REQUIRED FILES "
                "exactly."
            ),
        },
        {"role": "user", "content": user_msg},
    ]


def call_ollama(model: str, messages: list[dict], num_ctx: int, timeout: int) -> str:
    payload = {
        "model": model,
        "stream": False,
        "options": {"num_ctx": num_ctx, "temperature": 0.1, "top_p": 0.8},
        "messages": messages,
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("message", {}).get("content", "")


# A "block" looks like:
#   <path>\n```<optional-lang>\n<content>\n```
# where <path> is a non-empty single line that does not itself start with
# whitespace or a backtick. We tolerate Windows-style separators by
# normalizing later.
BLOCK_RE = re.compile(
    r"(?:^|\n)(?P<path>[^\s`][^\n]*?)\n"
    r"```[a-zA-Z0-9_+\-]*\n"
    r"(?P<content>.*?)\n?"
    r"```",
    re.DOTALL,
)


def parse_blocks(response: str, valid_paths: set[str]) -> dict[str, str]:
    """Return path -> content for every fenced block whose path matches a valid target."""
    found: dict[str, str] = {}
    for m in BLOCK_RE.finditer(response):
        raw_path = m.group("path").strip().rstrip(":").strip("`'\" ")
        norm = raw_path.replace("\\", "/")
        if norm in valid_paths:
            found[norm] = m.group("content")
    return found


def write_files(root: Path, blocks: dict[str, str]) -> list[Path]:
    written: list[Path] = []
    for rel, content in blocks.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Trailing newline for sanity.
        if not content.endswith("\n"):
            content += "\n"
        dest.write_text(content, encoding="utf-8")
        written.append(dest)
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="Path to the spec markdown file.")
    ap.add_argument(
        "--target",
        action="append",
        required=True,
        help="Required output file (repeatable), relative to --root.",
    )
    ap.add_argument("--root", required=True, help="Repo / git root directory.")
    ap.add_argument("--model", default="qwen3-coder:30b")
    ap.add_argument("--num-ctx", type=int, default=32768)
    ap.add_argument("--timeout", type=int, default=900, help="Seconds to wait on Ollama.")
    ap.add_argument(
        "--retries",
        type=int,
        default=2,
        help="If targets are missing from the response, retry up to this many times.",
    )
    ap.add_argument(
        "--raw-response",
        help="If set, write the raw model response to this path for debugging.",
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    spec_path = Path(args.spec).resolve()
    if not spec_path.is_file():
        print(f"ERROR: spec not found: {spec_path}", file=sys.stderr)
        return 2
    spec_text = spec_path.read_text(encoding="utf-8")

    # Normalize target separators - the model sees forward slashes.
    targets = [t.replace("\\", "/") for t in args.target]
    valid_paths = set(targets)

    print(f"[ollama-build] model     : {args.model}")
    print(f"[ollama-build] num_ctx   : {args.num_ctx}")
    print(f"[ollama-build] root      : {root}")
    print(f"[ollama-build] spec      : {spec_path}  ({len(spec_text)} chars)")
    print(f"[ollama-build] targets   : {len(targets)} files")
    for t in targets:
        print(f"                {t}")
    print(f"[ollama-build] retries   : up to {args.retries}")
    sys.stdout.flush()

    messages = build_messages(spec_text, targets, root_prefix=targets[0].split("/")[0])

    written_paths: list[Path] = []
    missing = set(targets)
    full_response = ""

    for attempt in range(args.retries + 1):
        if attempt > 0:
            # Nudge the model to emit only the missing files next round.
            still_needed = "\n".join(f"   - {t}" for t in sorted(missing))
            messages.append({"role": "assistant", "content": full_response})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Some required files were missing or malformed. Re-emit "
                        f"ONLY these files now, in the same format:\n{still_needed}\n"
                        "Do not include any prose."
                    ),
                }
            )

        print(f"\n[ollama-build] attempt {attempt + 1}/{args.retries + 1} ...")
        sys.stdout.flush()
        t0 = time.monotonic()
        try:
            full_response = call_ollama(
                args.model, messages, args.num_ctx, args.timeout
            )
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"ERROR: Ollama call failed: {e}", file=sys.stderr)
            return 2
        elapsed = time.monotonic() - t0
        print(
            f"[ollama-build] got {len(full_response)} chars in {elapsed:.1f}s "
            f"({len(full_response) / max(elapsed, 0.001):.0f} chars/s)"
        )

        if args.raw_response:
            raw_path = Path(args.raw_response)
            existing = raw_path.read_text(encoding="utf-8") if raw_path.exists() else ""
            raw_path.write_text(
                existing + f"\n===== attempt {attempt + 1} =====\n" + full_response,
                encoding="utf-8",
            )

        blocks = parse_blocks(full_response, valid_paths)
        new_blocks = {k: v for k, v in blocks.items() if k in missing}
        if not new_blocks:
            print(
                f"[ollama-build] no new valid blocks this attempt; "
                f"still missing: {sorted(missing)}"
            )
            continue

        new_written = write_files(root, new_blocks)
        for p in new_written:
            size = p.stat().st_size
            rel = p.relative_to(root).as_posix()
            print(f"[ollama-build] wrote {size:>6} B  {rel}")
        written_paths.extend(new_written)
        missing -= set(new_blocks.keys())

        if not missing:
            break

        print(f"[ollama-build] still missing: {sorted(missing)}")

    if missing:
        print(f"\n[ollama-build] FAIL - never received valid blocks for: {sorted(missing)}", file=sys.stderr)
        return 3

    # Verify nothing came out zero bytes.
    zero = [p for p in written_paths if p.stat().st_size == 0]
    if zero:
        # An empty __init__.py is legitimate; only fail if a non-__init__ is empty.
        bad = [p for p in zero if p.name != "__init__.py"]
        if bad:
            print(f"\n[ollama-build] FAIL - wrote zero bytes for: {bad}", file=sys.stderr)
            return 3

    print(f"\n[ollama-build] OK - all {len(targets)} targets written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
