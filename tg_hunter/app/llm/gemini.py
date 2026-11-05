from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Sequence

import httpx

from app.llm.base import LLMError, LLMUnavailable, b64, parse_json_object, post_with_retry, sniff_mime

_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        fallback_models: Sequence[str] = (),
        timeout: float = 90,
        max_retries: int = 4,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._models = [model, *[m for m in fallback_models if m != model]]
        self.last_model_used: str | None = None
        self._max_retries = max_retries
        self._sleep = sleep
        self._headers = {"x-goog-api-key": api_key, "content-type": "application/json"}
        self._http = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def generate_json(self, *, system: str, user: str, images: Sequence[bytes] = ()) -> dict:
        parts = [{"text": user}] + [{"inlineData": {"mimeType": sniff_mime(i), "data": b64(i)}} for i in images]
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192, "responseMimeType": "application/json"},
        }
        data = None
        for i, model in enumerate(self._models):
            try:
                data = await post_with_retry(
                    self._http,
                    _URL.format(model=model),
                    headers=self._headers,
                    payload=payload,
                    max_retries=self._max_retries,
                    sleep=self._sleep,
                )
                self.last_model_used = model
                break
            except LLMUnavailable:
                if i == len(self._models) - 1:
                    raise
        assert data is not None
        cands = data.get("candidates") or []
        if not cands:
            raise LLMError(f"Gemini javob bermadi (bloklangan?): {data.get('promptFeedback')}")
        cand = cands[0]
        text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
        if not text:
            raise LLMError(f"Gemini bo'sh javob, finishReason={cand.get('finishReason')}")
        return parse_json_object(text)

    async def aclose(self) -> None:
        await self._http.aclose()
