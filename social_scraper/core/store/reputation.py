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
