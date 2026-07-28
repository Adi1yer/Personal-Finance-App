"""HTTP client for local Ollama."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx


class OllamaError(Exception):
    pass


def ollama_base_url(settings: dict[str, Any] | None = None) -> str:
    if settings:
        return str(settings.get("ollama_url", "http://localhost:11434")).rstrip("/")
    return "http://localhost:11434"


def ollama_model(settings: dict[str, Any] | None = None) -> str:
    if settings:
        return str(settings.get("ollama_model", "llama3.1:latest"))
    return "llama3.1:latest"


def model_is_available(configured: str, installed: list[str]) -> bool:
    """Match llama3.1 ↔ llama3.1:latest style tags."""
    configured = (configured or "").strip()
    if not configured:
        return False
    names = set(installed or [])
    if configured in names:
        return True
    base = configured.split(":")[0]
    return any(m == base or m.startswith(base + ":") for m in names)


def health_check(base_url: str | None = None) -> dict[str, Any]:
    url = (base_url or ollama_base_url()).rstrip("/")
    try:
        with httpx.Client(timeout=5.0) as client:
            res = client.get(f"{url}/api/tags")
            res.raise_for_status()
            data = res.json()
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            return {"connected": True, "models": models}
    except Exception as e:
        return {"connected": False, "error": str(e), "models": []}


def chat_message(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Return the full assistant message dict (content + optional tool_calls)."""
    url = (base_url or ollama_base_url()).rstrip("/")
    payload: dict[str, Any] = {
        "model": model or ollama_model(),
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
    try:
        with httpx.Client(timeout=180.0) as client:
            res = client.post(f"{url}/api/chat", json=payload)
            res.raise_for_status()
            data = res.json()
            msg = data.get("message") or {}
            return {
                "role": msg.get("role") or "assistant",
                "content": msg.get("content") or "",
                "tool_calls": msg.get("tool_calls") or [],
            }
    except Exception as e:
        raise OllamaError(str(e)) from e


def chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    base_url: str | None = None,
) -> str:
    msg = chat_message(messages, model=model, tools=tools, base_url=base_url)
    return str(msg.get("content") or "")


async def chat_stream(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    base_url: str | None = None,
) -> AsyncIterator[str]:
    url = (base_url or ollama_base_url()).rstrip("/")
    payload = {
        "model": model or ollama_model(),
        "messages": messages,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=180.0) as client:
        async with client.stream("POST", f"{url}/api/chat", json=payload) as res:
            res.raise_for_status()
            async for line in res.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = chunk.get("message", {}).get("content")
                if content:
                    yield content
