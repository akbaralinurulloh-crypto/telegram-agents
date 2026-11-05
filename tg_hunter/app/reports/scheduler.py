"""Hisobotlarni jadval bo'yicha yuborish (Asia/Tashkent).

MUHIM: jadval CronTrigger (kutish taymeri) emas, har 30 soniyada HAQIQIY soatga qarab tekshiradigan `tick` ga tayanadi.
Sabab: Docker Desktop (WSL2) da kompyuter uxlaganda Linux taymerlari to'xtaydi — cron taymerlari uyqu davomiyligicha kechikib,
13:00/20:00 hisobotlari jimgina o'tib ketardi. `tick` esa uyg'ongach 30 soniya ichida soatni ko'radi va o'tkazib yuborilganini
KECHIKKAN belgisi bilan yuboradi.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot_admin import is_dry_run, is_paused
from app.db.repository import Repository
from app.reports.builder import Period, build_report, period_for, system_lines
from app.utils.logging import get_logger
from app.utils.text import TG_LIMIT, split_message

log = get_logger("reports")
HEARTBEAT_KEY = "last_seen"
FIRST_START_KEY = "first_started_at"
LATE_AFTER = timedelta(minutes=15)  # rejalashtirilgan vaqtdan shuncha keyin yuborilsa — "kechikkan" deb belgilanadi

chunks = split_message  # eski nom (testlar va tashqi chaqiruvlar uchun)


async def heartbeat(repo: Repository) -> None:
    await repo.set_kv(HEARTBEAT_KEY, datetime.now(timezone.utc).isoformat())


def _span(gap: timedelta) -> str:
    h = gap.total_seconds() / 3600
    if h >= 48:
        return f"{h / 24:.1f} kun"
    if h >= 1:
        return f"{h:.1f} soat"
    return f"{int(gap.total_seconds() // 60)} daqiqa"


async def downtime_notice(repo: Repository, now: datetime, tz: ZoneInfo, min_minutes: float = 10) -> str | None:
    """Oxirgi faollikdan beri `min_minutes` dan ko'p o'tgan bo'lsa — ishga tushganda ogohlantirish matni."""
    raw = await repo.get_kv(HEARTBEAT_KEY)
    if not raw:
        return None
    last = datetime.fromisoformat(raw)
    last = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
    gap = now.astimezone(timezone.utc) - last
    if gap.total_seconds() < min_minutes * 60:
        return None
    return (
        f"⚠️ Agent {_span(gap)} davomida ishlamagan edi (oxirgi faollik: {last.astimezone(tz).strftime('%d.%m %H:%M')}).\n"
        "Shu vaqtda kelgan postlar va rejalashtirilgan hisobotlar o'tkazib yuborilgan bo'lishi mumkin.\n"
        "Sabab: kompyuter o'chiq/uyquda yoki Docker to'xtagan. Uzluksiz ishlash uchun VPS kerak."
    )


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
        grace: timedelta = timedelta(hours=12),
        sleep_gap: timedelta = timedelta(minutes=5),
        on_wake: Callable[[], Awaitable[None]] | None = None,
    ):
        self.repo, self.send, self.slots, self.target, self.sources = repo, send, slots, target, sources
        self.tz = ZoneInfo(tz)
        self.connected, self.dry_default = connected, dry_run_default
        self.grace, self.sleep_gap, self.on_wake = grace, sleep_gap, on_wake
        self._now = now or (lambda: datetime.now(self.tz))
        self._last_tick: datetime | None = None

    @staticmethod
    def key(day, slot: str) -> str:
        return f"{day.isoformat()}@{slot}"

    def last_occurrence(self, slot: str, now: datetime) -> datetime:
        """`slot` ("HH:MM") ning `now` dan oldingi (yoki aynan o'sha) eng so'nggi vaqti."""
        h, m = (int(x) for x in slot.split(":"))
        cand = datetime.combine(now.astimezone(self.tz).date(), time(h, m), tzinfo=self.tz)
        return cand if cand <= now else cand - timedelta(days=1)

    async def _system(self) -> list[str]:
        return await system_lines(self.repo, self.connected(), await is_dry_run(self.repo, self.dry_default), await is_paused(self.repo), tz=self.tz)

    async def run_slot(self, slot: str, scheduled: datetime | None = None) -> bool:
        """Hisobotni yig'ib yuboradi. Allaqachon yuborilgan bo'lsa qayta yubormaydi. Yuborilmasa DB'da saqlanadi va `retry_unsent` qayta urinadi."""
        now = self._now()
        scheduled = scheduled or self.last_occurrence(slot, now)
        period = period_for(slot, self.slots, scheduled, self.tz)
        pkey = self.key(scheduled.astimezone(self.tz).date(), slot)
        row = await self.repo.ensure_report(pkey, "full" if period.full_day else "regular", scheduled)
        if row.sent_at is not None:
            return True
        late = scheduled.astimezone(self.tz).strftime("%d.%m %H:%M") if now - scheduled > LATE_AFTER else None
        text = await build_report(self.repo, period, target=self.target, sources=self.sources, system_lines=await self._system(), late_from=late)
        return await self._deliver(pkey, text)

    async def preview_now(self) -> str:
        """Bugungi kunning hozirgacha bo'lgan hisobotini darrov yig'adi (`/report`). Jadvalga va yuborilgan-belgisiga ta'sir qilmaydi."""
        now = self._now()
        start = datetime.combine(now.date(), time(0, 0), tzinfo=self.tz)
        period = Period(start.astimezone(timezone.utc), now.astimezone(timezone.utc), f"{start:%d.%m %H:%M} → {now:%d.%m %H:%M}", True)
        return await build_report(self.repo, period, target=self.target, sources=self.sources, system_lines=await self._system(), title="📊 HISOBOT (bugun, hozirgacha)")

    async def _deliver(self, pkey: str, text: str) -> bool:
        try:
            for part in split_message(text):
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
            late = sched.astimezone(self.tz).strftime("%d.%m %H:%M")
            if not r.text:  # yig'ish ham muvaffaqiyatsiz bo'lgan: qaytadan yig'amiz
                slot = r.period_key.split("@")[1]
                period = period_for(slot, self.slots, sched, self.tz)
                text = await build_report(self.repo, period, target=self.target, sources=self.sources, system_lines=await self._system(), late_from=late)
            else:
                text = f"⏰ Kechikkan hisobot ({late} da yuborilishi kerak edi)\n\n{r.text}" if "Kechikkan" not in r.text else r.text
            sent += await self._deliver(r.period_key, text)
        return sent

    async def _first_started(self, now: datetime) -> datetime:
        raw = await self.repo.get_kv(FIRST_START_KEY)
        if raw:
            return datetime.fromisoformat(raw)
        await self.repo.set_kv(FIRST_START_KEY, now.astimezone(timezone.utc).isoformat())
        return now

    async def _pulse(self, now: datetime) -> None:
        """Har tick: 'tirik' belgisi yozadi; oldingi tickdan beri uzoq vaqt o'tgan bo'lsa — kompyuter uxlagan: adminni ogohlantiradi va Telegram yangiliklarini qayta oladi."""
        last, self._last_tick = self._last_tick, now
        await heartbeat(self.repo)
        if last is None or now - last <= self.sleep_gap:
            return
        gap = now - last
        log.warning("wake_detected", gap_seconds=int(gap.total_seconds()))
        try:
            await self.send(
                f"💤 Agent {_span(gap)} davomida to'xtab turgan edi (oxirgi faollik: {last.astimezone(self.tz).strftime('%d.%m %H:%M')}). "
                "Ehtimol, kompyuter uyquga ketgan.\nO'tkazib yuborilgan hisobotlar kechikib yuboriladi, kanallardagi yangi postlar qayta tekshiriladi."
            )
        except Exception:
            log.exception("wake_notice_failed")
        if self.on_wake:
            try:
                await self.on_wake()
            except Exception:
                log.exception("on_wake_failed")

    async def tick(self) -> None:
        """Har 30 soniyada: haqiqiy soatga qarab muddati kelgan (va hali yuborilmagan) hisobotlarni yuboradi."""
        now = self._now()
        await self._pulse(now)
        first = await self._first_started(now)
        for slot in self.slots:
            due = self.last_occurrence(slot, now)
            if due < first or now - due > self.grace:
                continue  # agent ishga tushishidan oldingi yoki juda eski davr
            if await self.repo.get_report(self.key(due.astimezone(self.tz).date(), slot)) is not None:
                continue  # yuborilgan; yuborilmagan bo'lsa retry_unsent ko'radi
            await self.run_slot(slot, due)

    def start(self) -> AsyncIOScheduler:
        sch = AsyncIOScheduler(timezone=self.tz)
        sch.add_job(self.tick, "interval", seconds=30, id="tick", coalesce=True, max_instances=1, misfire_grace_time=None, next_run_time=datetime.now(self.tz))
        sch.add_job(self.retry_unsent, "interval", minutes=10, id="report_retry", coalesce=True)
        sch.start()
        return sch
