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
