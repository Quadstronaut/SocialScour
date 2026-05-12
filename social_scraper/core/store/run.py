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
