from __future__ import annotations

import asyncio
import base64
import json
import re
from typing import Awaitable, Callable, Protocol, Sequence

import httpx


class LLMError(Exception):
    """LLM chaqiruvi muvaffaqiyatsiz yoki javob yaroqsiz. Chaqiruvchi fail-closed ishlaydi."""


class LLMUnavailable(LLMError):
    """Qayta urinishlardan keyin ham xizmat band/uzilgan (zaxira modelga o'tish mumkin)."""


class LLMClient(Protocol):
    async def generate_json(self, *, system: str, user: str, images: Sequence[bytes] = ()) -> dict: ...


def sniff_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_json_object(text: str) -> dict:
    try:
        obj = json.loads(_FENCE.sub("", text.strip()))
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON emas: {text[:120]!r}") from exc
    if not isinstance(obj, dict):
        raise LLMError("JSON obyekt emas")
    return obj


RETRYABLE = {408, 429, 500, 502, 503, 504, 529}


async def post_with_retry(
    http: httpx.AsyncClient,
    url: str,
    *,
    headers: dict,
    payload: dict,
    max_retries: int,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict:
    """429/5xx va tarmoq xatolarida eksponensial kutish bilan qayta uriniladi (Retry-After hurmat qilinadi)."""
    last = "noma'lum xato"
    for attempt in range(max_retries + 1):
        delay = min(2.0 * 2**attempt, 30.0)
        try:
            resp = await http.post(url, headers=headers, json=payload)
        except httpx.TransportError as exc:
            last = f"tarmoq: {exc.__class__.__name__}"
        else:
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError as exc:
                    raise LLMError("javob JSON emas") from exc
            last = f"HTTP {resp.status_code}: {resp.text[:200]}"
            if resp.status_code not in RETRYABLE:
                raise LLMError(last)
            ra = resp.headers.get("retry-after")
            if ra and ra.replace(".", "", 1).isdigit():
                delay = min(float(ra), 60.0)
        if attempt < max_retries:
            await sleep(delay)
    raise LLMUnavailable(f"{max_retries + 1} urinishdan keyin ham muvaffaqiyatsiz: {last}")
