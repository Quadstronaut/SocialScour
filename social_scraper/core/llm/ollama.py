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
