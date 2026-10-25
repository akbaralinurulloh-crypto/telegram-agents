from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import KV, AuditLog, ReportLog, SourceUnit, UnitHash, UnitMessage, utcnow


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

    async def add_hashes(self, unit_id: int, text_hash: str | None, phashes: list[str]) -> None:
        async with self._sm.begin() as s:
            if text_hash:
                s.add(UnitHash(unit_id=unit_id, kind="text", value=text_hash))
            for ph in dict.fromkeys(phashes):
                s.add(UnitHash(unit_id=unit_id, kind="phash", value=ph))

    # Xato yoki qo'lda ko'rishga tushgan postlar nusxalarini to'smaydi (aks holda kontent yo'qolardi).
    _NON_BLOCKING = ("error", "manual_review")

    async def find_by_text_hash(self, value: str, exclude_unit_id: int | None = None) -> int | None:
        async with self._sm() as s:
            q = (
                select(UnitHash.unit_id)
                .join(SourceUnit, SourceUnit.id == UnitHash.unit_id)
                .where(UnitHash.kind == "text", UnitHash.value == value, SourceUnit.state.not_in(self._NON_BLOCKING))
            )
            if exclude_unit_id is not None:
                q = q.where(UnitHash.unit_id != exclude_unit_id)
            return await s.scalar(q.order_by(UnitHash.unit_id).limit(1))

    async def known_phashes(self, exclude_unit_id: int | None = None) -> list[tuple[int, str]]:
        async with self._sm() as s:
            q = (
                select(UnitHash.unit_id, UnitHash.value)
                .join(SourceUnit, SourceUnit.id == UnitHash.unit_id)
                .where(UnitHash.kind == "phash", SourceUnit.state.not_in(self._NON_BLOCKING))
            )
            if exclude_unit_id is not None:
                q = q.where(UnitHash.unit_id != exclude_unit_id)
            return [(u, v) for u, v in (await s.execute(q)).all()]

    # ---- qarorlar ----
    async def set_state(self, unit_id: int, state: str) -> None:
        async with self._sm.begin() as s:
            u = await s.get(SourceUnit, unit_id)
            if u:
                u.state = state

    async def record_decision(
        self,
        unit_id: int,
        state: str,
        reason: str | None = None,
        *,
        score: float | None = None,
        caption: str | None = None,
        posted_ids: list[int] | None = None,
        dry_run: bool = False,
        detail: dict | None = None,
    ) -> None:
        async with self._sm.begin() as s:
            u = await s.get(SourceUnit, unit_id)
            if u is None:
                return
            u.state, u.decision_reason, u.decided_at, u.dry_run = state, reason, utcnow(), dry_run
            if score is not None:
                u.score = score
            if caption is not None:
                u.caption = caption
            if posted_ids is not None:
                u.posted_ids = posted_ids
            if detail is not None:
                u.decision_detail = detail
            s.add(AuditLog(unit_id=unit_id, event="decision", detail={"state": state, "reason": reason, "score": score, "dry_run": dry_run, **(detail or {})}))

    async def pending_units(self) -> list[SourceUnit]:
        async with self._sm() as s:
            q = select(SourceUnit).where(SourceUnit.state.in_(("received", "processing")), SourceUnit.deleted_at.is_(None)).order_by(SourceUnit.id)
            return list((await s.scalars(q)).all())

    async def units_created_between(self, start: datetime, end: datetime) -> list[SourceUnit]:
        async with self._sm() as s:
            q = select(SourceUnit).where(SourceUnit.created_at >= start, SourceUnit.created_at < end).order_by(SourceUnit.id)
            return list((await s.scalars(q)).all())

    async def last_units(self, n: int) -> list[SourceUnit]:
        async with self._sm() as s:
            return list((await s.scalars(select(SourceUnit).order_by(SourceUnit.id.desc()).limit(n))).all())

    async def count_pending(self) -> int:
        async with self._sm() as s:
            return int(await s.scalar(select(func.count()).select_from(SourceUnit).where(SourceUnit.state.in_(("received", "processing")), SourceUnit.deleted_at.is_(None))) or 0)

    # ---- ish vaqti sozlamalari ----
    async def get_kv(self, key: str, default: str | None = None) -> str | None:
        async with self._sm() as s:
            row = await s.get(KV, key)
            return row.value if row else default

    async def set_kv(self, key: str, value: str) -> None:
        async with self._sm.begin() as s:
            row = await s.get(KV, key)
            if row:
                row.value = value
            else:
                s.add(KV(key=key, value=value))

    # ---- hisobotlar ----
    async def ensure_report(self, period_key: str, kind: str, scheduled_for: datetime) -> ReportLog:
        scheduled_for = scheduled_for.astimezone(timezone.utc)  # SQLite zonani saqlamaydi: doim UTC
        async with self._sm.begin() as s:
            row = await s.scalar(select(ReportLog).where(ReportLog.period_key == period_key))
            if row is None:
                row = ReportLog(period_key=period_key, kind=kind, scheduled_for=scheduled_for)
                s.add(row)
                await s.flush()
            return row

    async def save_report_attempt(self, period_key: str, text: str, sent: bool) -> None:
        async with self._sm.begin() as s:
            row = await s.scalar(select(ReportLog).where(ReportLog.period_key == period_key))
            if row:
                row.attempts += 1
                row.text = text
                if sent:
                    row.sent_at = utcnow()

    async def unsent_reports(self) -> list[ReportLog]:
        async with self._sm() as s:
            return list((await s.scalars(select(ReportLog).where(ReportLog.sent_at.is_(None)).order_by(ReportLog.scheduled_for))).all())
