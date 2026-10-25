from __future__ import annotations

from app.db.repository import NormalizedUnit


def media_kind(msg) -> str | None:
    """Telethon xabaridan media turini aniqlaydi (matn-only bo'lsa None)."""
    if getattr(msg, "photo", None):
        return "photo"
    if getattr(msg, "gif", None):
        return "gif"
    if getattr(msg, "video", None) or getattr(msg, "video_note", None):
        return "video"
    if getattr(msg, "sticker", None):
        return "sticker"
    if getattr(msg, "voice", None) or getattr(msg, "audio", None):
        return "audio"
    if getattr(msg, "document", None):
        return "document"
    return None


def normalize(messages: list, channel_id: int, channel_title: str) -> NormalizedUnit:
    """Bitta xabar yoki albom xabarlarini bitta ishlov birligiga aylantiradi."""
    msgs = sorted(messages, key=lambda m: m.id)
    text = next(((m.message or "").strip() for m in msgs if (m.message or "").strip()), "")
    kinds = [k for m in msgs if (k := media_kind(m))]
    return NormalizedUnit(
        channel_id=channel_id,
        channel_title=channel_title,
        message_ids=[m.id for m in msgs],
        grouped_id=getattr(msgs[0], "grouped_id", None),
        text=text,
        media_kinds=kinds,
        date=msgs[0].date,
    )
