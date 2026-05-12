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
