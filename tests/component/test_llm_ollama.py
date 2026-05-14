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


def test_embed_returns_vectors_and_honors_model_override():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = json.loads(req.content.decode("utf-8"))
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    client = OllamaClient(
        model="default-model",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    vectors = client.embed(["hello", "world"], model="bge-m3:latest")
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["url"].endswith("/api/embed")
    assert captured["body"]["model"] == "bge-m3:latest"
    assert captured["body"]["input"] == ["hello", "world"]


def test_embed_raises_ollama_error_on_http_failure():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope", request=req)

    client = OllamaClient(
        model="x",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(OllamaError):
        client.embed(["text"])


def test_embed_empty_input_returns_empty_list():
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP should not be called for empty input")

    client = OllamaClient(
        model="x",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.embed([]) == []
