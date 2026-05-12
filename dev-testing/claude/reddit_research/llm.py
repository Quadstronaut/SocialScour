"""OpenAI-SDK wrapper pointed at Ollama."""
from __future__ import annotations

from collections.abc import Iterator

import openai
from pydantic import BaseModel, ValidationError


class LLMError(Exception):
    pass


class LLM:
    def __init__(
        self,
        model: str = "qwen3-coder:30b",
        base_url: str = "http://localhost:11434/v1",
    ) -> None:
        self.model = model
        self.client = openai.OpenAI(base_url=base_url, api_key="ollama")

    def ping(self) -> bool:
        try:
            self.client.models.list(timeout=2.0)
            return True
        except Exception:
            return False

    def json_call(self, system: str, user: str, schema_cls: type[BaseModel]) -> BaseModel:
        def _call(user_msg: str) -> BaseModel:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or ""
            return schema_cls.model_validate_json(raw)

        try:
            return _call(user)
        except ValidationError as exc:
            corrective = f"{user}\n\nYour previous output failed schema validation: {exc}. Try again."
            try:
                return _call(corrective)
            except ValidationError as exc2:
                raise LLMError(f"LLM output failed schema validation twice: {exc2}") from exc2

    def text_call(self, system: str, user: str, stream: bool = False) -> str | Iterator[str]:
        if stream:
            return self._stream(system, user)
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    def _stream(self, system: str, user: str) -> Iterator[str]:
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=True,
        )
        for chunk in stream:
            yield chunk.choices[0].delta.content or ""
