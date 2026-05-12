"""Persistent reputation scoring per v1.spec §12."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _empty_store() -> dict:
    return {"version": Reputation.VERSION, "topic_areas": {}}


def _ensure_sub(area_data: dict, sub: str) -> dict:
    subs = area_data.setdefault("subs", {})
    if sub not in subs:
        subs[sub] = {"score": 0, "last_useful_utc": None, "promoted": False}
    return subs[sub]


class Reputation:
    VERSION = 1

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict = {}

    def load(self) -> dict:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = _empty_store()
        else:
            self._data = _empty_store()
        return self._data

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=self._path.parent, prefix=".rep_tmp_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def existing_areas(self) -> list[str]:
        return list(self._data.get("topic_areas", {}).keys())

    def top_reputed(self, area: str, n: int = 3) -> list[str]:
        subs: dict[str, dict] = (
            self._data.get("topic_areas", {}).get(area, {}).get("subs", {})
        )
        ranked = sorted(
            subs.items(),
            key=lambda kv: (kv[1].get("score", 0), kv[1].get("last_useful_utc") or ""),
            reverse=True,
        )
        return [sub for sub, _ in ranked[:n]]

    def promoted_subs(self, area: str) -> list[str]:
        subs: dict[str, dict] = (
            self._data.get("topic_areas", {}).get(area, {}).get("subs", {})
        )
        return [sub for sub, meta in subs.items() if meta.get("promoted", False)]

    def auto_update(
        self, area: str, sub_signals: dict[str, dict]
    ) -> dict[str, int]:
        areas = self._data.setdefault("topic_areas", {})
        area_data = areas.setdefault(area, {"subs": {}})
        changes: dict[str, int] = {}

        for sub, sig in sub_signals.items():
            density: float = sig.get("signal_density", 0.0)
            n_posts: int = sig.get("n_posts", 0)
            entry = _ensure_sub(area_data, sub)

            if density > 0.6:
                entry["score"] = entry.get("score", 0) + 1
                entry["last_useful_utc"] = _now_iso()
                changes[sub] = entry["score"]
            elif density < 0.3 and n_posts >= 3:
                if not entry.get("promoted", False):
                    new_score = max(-3, entry.get("score", 0) - 1)
                    entry["score"] = new_score
                    changes[sub] = new_score

        return changes

    def promote(self, area: str, sub: str) -> None:
        area_data = self._data.setdefault("topic_areas", {}).setdefault(area, {"subs": {}})
        entry = _ensure_sub(area_data, sub)
        entry["promoted"] = True

    def demote(self, area: str, sub: str) -> None:
        area_data = self._data.setdefault("topic_areas", {}).setdefault(area, {"subs": {}})
        entry = _ensure_sub(area_data, sub)
        entry["promoted"] = False
        entry["score"] = 0
