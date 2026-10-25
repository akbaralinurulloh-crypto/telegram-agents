"""Kanalga joylash (aiogram). DRY-RUN'da kanalga emas, adminga ko'rsatadi."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo

from app.utils.logging import get_logger

log = get_logger("publisher")

CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096
ALBUM_LIMIT = 10


@dataclass
class MediaItem:
    path: Path
    kind: str  # "photo" | "video"


@dataclass
class PostPlan:
    """Joylanadigan narsa: matn, yoki media (albom bo'lishi mumkin) + sarlavha + (sig'masa) alohida matn."""

    media: list[MediaItem]
    caption: str = ""
    text: str = ""  # media bo'lmasa — post matni; media bo'lsa va sarlavhaga sig'masa — alohida xabar


def split_text(text: str, limit: int = TEXT_LIMIT) -> list[str]:
    text = text.strip()
    parts: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        cut = cut if cut > limit // 2 else limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    return parts


def build_plan(cleaned_text: str, caption: str, media: list[MediaItem]) -> PostPlan:
    """Media bo'lsa: sarlavha = asl matn + izoh (1024 ga sig'sa). Sig'masa — sarlavha = izoh, asl matn alohida xabar."""
    cleaned_text, caption = cleaned_text.strip(), caption.strip()
    if not media:
        return PostPlan([], text=cleaned_text)
    combined = f"{cleaned_text}\n\n{caption}".strip() if caption else cleaned_text
    if len(combined) <= CAPTION_LIMIT:
        return PostPlan(media, caption=combined)
    return PostPlan(media, caption=caption[:CAPTION_LIMIT], text=cleaned_text)


class Publisher(Protocol):
    async def publish(self, chat_id: int | str, plan: PostPlan) -> list[int]: ...


class AiogramPublisher:
    def __init__(self, bot, *, max_retries: int = 5, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.bot, self.max_retries, self._sleep = bot, max_retries, sleep

    async def _call(self, fn, *args, **kwargs):
        """FloodWait (TelegramRetryAfter) va tarmoq xatolarida qayta uriniladi."""
        for attempt in range(self.max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except TelegramRetryAfter as exc:
                log.warning("flood_wait", seconds=exc.retry_after)
                if attempt == self.max_retries:
                    raise
                await self._sleep(exc.retry_after + 1)
            except TelegramNetworkError:
                if attempt == self.max_retries:
                    raise
                await self._sleep(min(2.0 * 2**attempt, 30))

    async def publish(self, chat_id: int | str, plan: PostPlan) -> list[int]:
        ids: list[int] = []
        if not plan.media:
            for part in split_text(plan.text):
                ids.append((await self._call(self.bot.send_message, chat_id, part)).message_id)
            return ids
        if len(plan.media) == 1:
            m = plan.media[0]
            send = self.bot.send_photo if m.kind == "photo" else self.bot.send_video
            kw = {"photo": FSInputFile(m.path)} if m.kind == "photo" else {"video": FSInputFile(m.path), "supports_streaming": True}
            ids.append((await self._call(send, chat_id, caption=plan.caption or None, **kw)).message_id)
        else:
            group = [
                (InputMediaPhoto if m.kind == "photo" else InputMediaVideo)(media=FSInputFile(m.path), caption=(plan.caption or None) if i == 0 else None)
                for i, m in enumerate(plan.media[:ALBUM_LIMIT])
            ]
            ids += [msg.message_id for msg in await self._call(self.bot.send_media_group, chat_id, group)]
        for part in split_text(plan.text):  # sarlavhaga sig'magan asl matn
            ids.append((await self._call(self.bot.send_message, chat_id, part)).message_id)
        return ids


def message_link(target_channel: str, message_id: int) -> str:
    t = target_channel.strip()
    if t.startswith("@"):
        return f"https://t.me/{t[1:]}/{message_id}"
    if t.lstrip("-").isdigit():
        n = t.lstrip("-")
        n = n[3:] if n.startswith("100") else n
        return f"https://t.me/c/{n}/{message_id}"
    return f"https://t.me/{t}/{message_id}"
