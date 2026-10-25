from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Sequence

import httpx

from app.llm.base import LLMError, b64, post_with_retry, sniff_mime

_URL = "https://api.anthropic.com/v1/messages"
_TOOL = {
    "name": "respond",
    "description": "Natijani JSON obyekt sifatida qaytaring.",
    "input_schema": {"type": "object", "additionalProperties": True},
}


class AnthropicClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout: float = 90,
        max_retries: int = 4,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._model = model
        self._max_retries = max_retries
        self._sleep = sleep
        self._headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        self._http = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def generate_json(self, *, system: str, user: str, images: Sequence[bytes] = ()) -> dict:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": sniff_mime(i), "data": b64(i)}} for i in images
        ] + [{"type": "text", "text": user}]
        payload = {
            "model": self._model,
            "max_tokens": 2048,
            "temperature": 0.2,
            "system": system,
            "messages": [{"role": "user", "content": content}],
            "tools": [_TOOL],
            "tool_choice": {"type": "tool", "name": "respond"},
        }
        data = await post_with_retry(
            self._http, _URL, headers=self._headers, payload=payload, max_retries=self._max_retries, sleep=self._sleep
        )
        for block in data.get("content", []):
            if block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
                return block["input"]
        raise LLMError(f"Claude tool_use qaytarmadi, stop_reason={data.get('stop_reason')}")

    async def aclose(self) -> None:
        await self._http.aclose()
