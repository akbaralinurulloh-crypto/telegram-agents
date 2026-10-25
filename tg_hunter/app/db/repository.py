from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditLog, SourceUnit, UnitMessage, utcnow


@dataclass(frozen=True)
class NormalizedUnit:
    channel_id: int
    channel_title: str
    message_ids: list[int]
    grouped_id: int | None
    text: str
    media_kinds: list[str]
    date: datetime


@dataclass(frozen=True)
class EditResult:
    unit: SourceUnit
    text_changed: bool


class Repository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]):
        self._sm = sessionmaker

    async def add_unit(self, u: NormalizedUnit) -> tuple[SourceUnit, bool]:
        """Idempotent: bir xil xabar qayta kelsa mavjud yozuv qaytadi (created=False)."""
        async with self._sm.begin() as s:
            existing = await s.scalar(
                select(SourceUnit)
                .join(UnitMessage)
                .where(UnitMessage.channel_id == u.channel_id, UnitMessage.message_id.in_(u.message_ids))
            )
            if existing:
                return existing, False
            unit = SourceUnit(
                channel_id=u.channel_id,
                channel_title=u.channel_title,
                grouped_id=u.grouped_id,
                text=u.text,
                media_kinds=u.media_kinds,
                source_date=u.date,
                messages=[UnitMessage(channel_id=u.channel_id, message_id=m) for m in u.message_ids],
            )
            s.add(unit)
            await s.flush()
            s.add(AuditLog(unit_id=unit.id, event="received", detail={"messages": u.message_ids}))
            return unit, True

    async def mark_edited(self, channel_id: int, message_id: int, new_text: str) -> EditResult | None:
        async with self._sm.begin() as s:
            unit = await s.scalar(
                select(SourceUnit)
                .join(UnitMessage)
                .where(UnitMessage.channel_id == channel_id, UnitMessage.message_id == message_id)
            )
            if unit is None:
                return None
            # Albomda sarlavha bitta xabarda; sarlavhasiz xabar tahriri matnni o'chirmasin.
            is_album = len(unit.messages) > 1
            changed = bool(new_text or not is_album) and new_text != unit.text
            if changed:
                unit.text = new_text
            unit.edited_at = utcnow()
            s.add(AuditLog(unit_id=unit.id, event="edited", detail={"message_id": message_id, "text_changed": changed}))
            return EditResult(unit, changed)

    async def mark_deleted(self, message_ids: list[int], channel_id: int | None = None) -> list[SourceUnit]:
        """Kanal xabarlari o'chirilganda Telegram `channel_id` bermasligi mumkin."""
        async with self._sm.begin() as s:
            q = select(SourceUnit).join(UnitMessage).where(UnitMessage.message_id.in_(message_ids)).distinct()
            if channel_id is not None:
                q = q.where(UnitMessage.channel_id == channel_id)
            units = list((await s.scalars(q)).all())
            fresh = [u for u in units if u.deleted_at is None]
            for u in fresh:
                u.deleted_at = utcnow()
                s.add(AuditLog(unit_id=u.id, event="deleted", detail={"state_before": u.state}))
            return fresh

    async def get_unit(self, unit_id: int) -> SourceUnit | None:
        async with self._sm() as s:
            return await s.get(SourceUnit, unit_id)

    async def audit(self, event: str, unit_id: int | None = None, **detail) -> None:
        async with self._sm.begin() as s:
            s.add(AuditLog(unit_id=unit_id, event=event, detail=detail))

    async def audit_events(self, unit_id: int) -> list[str]:
        async with self._sm() as s:
            rows = await s.scalars(select(AuditLog.event).where(AuditLog.unit_id == unit_id).order_by(AuditLog.id))
            return list(rows)
