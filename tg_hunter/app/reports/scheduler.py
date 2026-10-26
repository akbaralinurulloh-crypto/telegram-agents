"""Hisobotlarni jadval bo'yicha yuborish (Asia/Tashkent) va muvaffaqiyatsizlarini qayta yuborish."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.bot_admin import is_dry_run, is_paused
from app.db.repository import Repository
from app.reports.builder import build_report, period_for, system_lines
from app.utils.logging import get_logger

log = get_logger("reports")
TG_LIMIT = 4000


def chunks(text: str, limit: int = TG_LIMIT) -> list[str]:
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit and cur:
            out.append(cur)
            cur = ""
        cur += line[:limit] + "\n"
    return out + ([cur] if cur.strip() else [])


class ReportService:
    def __init__(
        self,
        repo: Repository,
        send: Callable[[str], Awaitable[None]],
        *,
        slots: list[str],
        tz: str,
        target: str,
        sources: list[str],
        connected: Callable[[], bool | None] = lambda: None,
        dry_run_default: bool = True,
        now: Callable[[], datetime] | None = None,
    ):
        self.repo, self.send, self.slots, self.target, self.sources = repo, send, slots, target, sources
        self.tz = ZoneInfo(tz)
        self.connected, self.dry_default = connected, dry_run_default
        self._now = now or (lambda: datetime.now(self.tz))

    @staticmethod
    def key(day, slot: str) -> str:
        return f"{day.isoformat()}@{slot}"

    async def run_slot(self, slot: str, scheduled: datetime | None = None) -> bool:
        """Hisobotni yig'ib yuboradi. Yuborilmasa DB'da saqlanadi va `retry_unsent` qayta urinadi."""
        scheduled = scheduled or self._now().replace(second=0, microsecond=0)
        period = period_for(slot, self.slots, scheduled, self.tz)
        pkey = self.key(scheduled.astimezone(self.tz).date(), slot)
        await self.repo.ensure_report(pkey, "full" if period.full_day else "regular", scheduled)
        sysl = await system_lines(self.repo, self.connected(), await is_dry_run(self.repo, self.dry_default), await is_paused(self.repo))
        text = await build_report(self.repo, period, target=self.target, sources=self.sources, system_lines=sysl)
        return await self._deliver(pkey, text)

    async def _deliver(self, pkey: str, text: str) -> bool:
        try:
            for part in chunks(text):
                await self.send(part)
        except Exception as exc:
            log.warning("report_send_failed", period=pkey, error=str(exc)[:120])
            await self.repo.save_report_attempt(pkey, text, sent=False)
            return False
        await self.repo.save_report_attempt(pkey, text, sent=True)
        return True

    async def retry_unsent(self) -> int:
        """Yuborilmagan hisobotlarni 'kechikkan' belgisi bilan qayta yuboradi."""
        sent = 0
        for r in await self.repo.unsent_reports():
            sched = r.scheduled_for if r.scheduled_for.tzinfo else r.scheduled_for.replace(tzinfo=timezone.utc)  # SQLite: UTC
            if not r.text:  # yig'ish ham muvaffaqiyatsiz bo'lgan: qaytadan yig'amiz
                slot = r.period_key.split("@")[1]
                period = period_for(slot, self.slots, sched, self.tz)
                sysl = await system_lines(self.repo, self.connected(), await is_dry_run(self.repo, self.dry_default), await is_paused(self.repo))
                text = await build_report(self.repo, period, target=self.target, sources=self.sources, system_lines=sysl, late_from=sched.astimezone(self.tz).strftime("%d.%m %H:%M"))
            else:
                late = sched.astimezone(self.tz).strftime("%d.%m %H:%M")
                text = f"⏰ Kechikkan hisobot ({late} da yuborilishi kerak edi)\n\n{r.text}" if "Kechikkan" not in r.text else r.text
            sent += await self._deliver(r.period_key, text)
        return sent

    def start(self) -> AsyncIOScheduler:
        sch = AsyncIOScheduler(timezone=self.tz)
        for slot in self.slots:
            h, m = slot.split(":")
            sch.add_job(self.run_slot, CronTrigger(hour=int(h), minute=int(m), timezone=self.tz), args=[slot], id=f"report_{slot}", misfire_grace_time=3600, coalesce=True)
        sch.add_job(self.retry_unsent, "interval", minutes=10, id="report_retry", coalesce=True)
        sch.start()
        return sch
