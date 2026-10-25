from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import update

from app.db.models import SourceUnit
from app.db.repository import NormalizedUnit
from app.reports.builder import build_report, period_for
from app.reports.scheduler import ReportService, chunks

TZ = ZoneInfo("Asia/Tashkent")
SLOTS = ["08:00", "13:00", "20:00"]


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_periods_in_tashkent_time():
    sched = datetime(2026, 10, 26, 8, 0, tzinfo=TZ)
    p = period_for("08:00", SLOTS, sched, TZ)  # kecha 20:00 -> bugun 08:00 (UTC+5)
    assert (p.start, p.end, p.full_day) == (utc(2026, 10, 25, 15), utc(2026, 10, 26, 3), False)
    p = period_for("13:00", SLOTS, datetime(2026, 10, 26, 13, 0, tzinfo=TZ), TZ)
    assert (p.start, p.end) == (utc(2026, 10, 26, 3), utc(2026, 10, 26, 8))
    p = period_for("20:00", SLOTS, datetime(2026, 10, 26, 20, 0, tzinfo=TZ), TZ)  # to'liq kun: 00:00 -> 20:00
    assert (p.start, p.end, p.full_day) == (utc(2026, 10, 25, 19), utc(2026, 10, 26, 15), True)
    assert "26.10 00:00" in p.label and "20:00" in p.label


async def seed(repo, created=utc(2026, 10, 26, 1)):
    specs = [
        ("Manba1", 1, "posted", None, 8.5, [11]),
        ("Manba1", 2, "rejected", "low_score", 5.0, None),
        ("Manba2", 3, "rejected", "commercial_ad", None, None),
        ("Manba2", 4, "rejected", "cover_failed", 7.4, None),
        ("Manba2", 5, "rejected", "duplicate", None, None),
        ("Manba1", 6, "rejected", "hadis_validator", 8.0, None),
        ("Manba1", 7, "manual_review", "phone_uncertain", None, None),
        ("Manba2", 8, "error", "exception", None, None),
        ("Manba2", 9, "dryrun", None, 9.2, None),
        ("Manba1", 10, "received", None, None, None),
    ]
    ids = []
    for ch, mid, state, reason, score, posted in specs:
        u, _ = await repo.add_unit(NormalizedUnit(-1 if ch == "Manba1" else -2, ch, [mid], None, f"matn {mid}", [], created))
        await repo.record_decision(u.id, state, reason, score=score, posted_ids=posted, detail={"error": "boom"} if state == "error" else None)
        ids.append(u.id)
    async with repo._sm.begin() as s:
        await s.execute(update(SourceUnit).values(created_at=created))
    return ids


async def test_report_contents(repo):
    await seed(repo)
    p = period_for("20:00", SLOTS, datetime(2026, 10, 26, 20, 0, tzinfo=TZ), TZ)
    text = await build_report(repo, p, target="@kanal", sources=["@a"], system_lines=["• Telethon: ulangan"])
    assert "KUNLIK TO'LIQ HISOBOT" in text and "(Asia/Tashkent)" in text
    assert "Ko'rildi: 10" in text and "Joylandi: 1" in text and "DRY-RUN (joylanardi): 1" in text
    assert "Rad etildi: 5" in text and "Qo'lda ko'rib chiqing: 1" in text and "Xato: 1" in text and "Navbatda: 1" in text
    for label in ("past ball: 1", "reklama: 1", "raqamni almashtirib bo'lmadi: 2", "dublikat: 1", "hadis validatori: 1", "xato: 1"):
        assert label in text, label
    assert "Manba1: ko'rildi 5, joylandi 1" in text and "Manba2: ko'rildi 5, joylandi 1" in text
    assert "https://t.me/kanal/11" in text and "8.5" in text
    assert "#" in text and "phone_uncertain" in text  # qo'lda ko'rish ro'yxati
    assert "Eng yaxshi" in text and "Eng past" in text and "Telethon: ulangan" in text
    assert "O'rtacha ball: 7.62" in text  # (8.5+5+7.4+8+9.2)/5 = 38.1/5


async def test_regular_report_has_no_best_worst_and_old_units_excluded(repo):
    await seed(repo, created=utc(2026, 10, 20))  # davrdan tashqarida
    p = period_for("13:00", SLOTS, datetime(2026, 10, 26, 13, 0, tzinfo=TZ), TZ)
    text = await build_report(repo, p, target="@kanal", sources=["@a", "@b"], system_lines=[])
    assert "Ko'rildi: 0" in text and "Eng yaxshi" not in text and "yangi xabar bo'lmadi" in text and "KUNLIK" not in text


class Sender:
    def __init__(self, fail_times=0):
        self.sent, self.fail = [], fail_times

    async def __call__(self, text):
        if self.fail:
            self.fail -= 1
            raise RuntimeError("bot down")
        self.sent.append(text)


def service(repo, send, now):
    return ReportService(repo, send, slots=SLOTS, tz="Asia/Tashkent", target="@kanal", sources=["@a"], now=lambda: now)


async def test_report_sent_once_and_logged(repo):
    s = Sender()
    svc = service(repo, s, datetime(2026, 10, 26, 8, 0, 5, tzinfo=TZ))
    assert await svc.run_slot("08:00")
    assert len(s.sent) == 1 and not await repo.unsent_reports()


async def test_failed_report_is_retried_and_marked_late(repo):
    s = Sender(fail_times=1)
    svc = service(repo, s, datetime(2026, 10, 26, 13, 0, 5, tzinfo=TZ))
    assert not await svc.run_slot("13:00") and s.sent == []
    assert len(await repo.unsent_reports()) == 1
    assert await svc.retry_unsent() == 1
    assert "Kechikkan hisobot (26.10 13:00" in s.sent[0] and "📊 Hisobot" in s.sent[0]
    assert not await repo.unsent_reports() and await svc.retry_unsent() == 0  # qayta yuborilmaydi


async def test_long_report_is_chunked_under_telegram_limit():
    parts = chunks("\n".join(f"satr {i} " + "x" * 80 for i in range(200)))
    assert len(parts) > 1 and all(len(p) <= 4096 for p in parts)


async def test_scheduler_registers_three_jobs_in_tashkent_time(repo):
    svc = service(repo, Sender(), datetime(2026, 10, 26, 7, 0, tzinfo=TZ))
    sch = svc.start()
    try:
        jobs = {j.id: j for j in sch.get_jobs()}
        assert {"report_08:00", "report_13:00", "report_20:00", "report_retry"} <= set(jobs)
        for slot in SLOTS:
            trig = jobs[f"report_{slot}"].trigger
            assert str(trig.timezone) == "Asia/Tashkent"
            f = {x.name: str(x) for x in trig.fields}
            assert f["hour"] == str(int(slot[:2])) and f["minute"] == "0"
        # keyingi ishga tushish aynan Toshkent vaqti bilan 08:00
        nxt = jobs["report_08:00"].trigger.get_next_fire_time(None, datetime(2026, 10, 26, 7, 0, tzinfo=TZ))
        assert nxt.hour == 8 and nxt.utcoffset().total_seconds() == 5 * 3600
    finally:
        sch.shutdown(wait=False)
