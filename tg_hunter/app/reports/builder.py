"""Hisobot matnini yig'ish (3 xil: 08:00, 13:00, 20:00 — to'liq kunlik)."""
from __future__ import annotations

import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.db.models import SourceUnit
from app.db.repository import Repository
from app.pipeline.publisher import message_link
from app.pipeline.reasons import CATEGORIES, category

POSTED = ("posted", "dryrun")


@dataclass
class Period:
    start: datetime  # UTC (aware)
    end: datetime
    label: str
    full_day: bool


def _hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def period_for(slot: str, slots: list[str], scheduled: datetime, tz: ZoneInfo) -> Period:
    """`scheduled` — rejalashtirilgan vaqt (tz da). Davr: oldingi slotdan shu slotgacha. Oxirgi slot — kunlik to'liq."""
    ordered = sorted(slots, key=_hhmm)
    i = ordered.index(slot)
    day = scheduled.astimezone(tz).date()
    end_local = datetime.combine(day, _hhmm(slot), tzinfo=tz)
    if i == 0:
        start_local = datetime.combine(day - timedelta(days=1), _hhmm(ordered[-1]), tzinfo=tz)
    else:
        start_local = datetime.combine(day, _hhmm(ordered[i - 1]), tzinfo=tz)
    full = i == len(ordered) - 1
    if full:
        start_local = datetime.combine(day, time(0, 0), tzinfo=tz)
    f = "%d.%m %H:%M"
    return Period(start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC")), f"{start_local.strftime(f)} → {end_local.strftime(f)}", full)


def _line(u: SourceUnit, target: str) -> str:
    link = message_link(target, u.posted_ids[0]) if u.posted_ids else f"#{u.id}"
    mark = "🧪" if u.state == "dryrun" else "✅"
    return f"{mark} {u.score:.1f} — {u.channel_title}: {link}" if u.score is not None else f"{mark} {link}"


async def build_report(
    repo: Repository,
    period: Period,
    *,
    target: str,
    sources: list[str],
    system_lines: list[str],
    late_from: str | None = None,
) -> str:
    units = await repo.units_created_between(period.start, period.end)
    seen = len(units)
    posted = [u for u in units if u.state in POSTED]
    rejected = [u for u in units if u.state == "rejected"]
    review = [u for u in units if u.state == "manual_review"]
    errors = [u for u in units if u.state == "error"]
    waiting = [u for u in units if u.state in ("received", "processing")]
    scored = [u.score for u in units if u.score is not None]

    out = []
    title = "📊 KUNLIK TO'LIQ HISOBOT" if period.full_day else "📊 Hisobot"
    out.append(f"{title}\n{period.label} (Asia/Tashkent)")
    if late_from:
        out.append(f"⏰ Kechikkan hisobot: {late_from} da yuborilishi kerak edi.")
    live = sum(u.state == "posted" for u in posted)
    dry = len(posted) - live
    out.append(
        f"\nKo'rildi: {seen}\nJoylandi: {live}" + (f"\n🧪 DRY-RUN (joylanardi): {dry}" if dry else "")
        + f"\nRad etildi: {len(rejected)}\nQo'lda ko'rib chiqing: {len(review)}\nXato: {len(errors)}\nNavbatda: {len(waiting)}"
        + (f"\nO'rtacha ball: {sum(scored) / len(scored):.2f}" if scored else "")
    )
    if rejected or review or errors:
        c = Counter(category(u.decision_reason) for u in rejected + review + errors)
        out.append("\nRad sabablari:\n" + "\n".join(f"• {CATEGORIES[k]}: {n}" for k, n in c.most_common()))

    per: dict[str, list[SourceUnit]] = defaultdict(list)
    for u in units:
        per[u.channel_title or str(u.channel_id)].append(u)
    if per:
        out.append("\nManbalar bo'yicha:")
        for name, us in sorted(per.items()):
            sc = [u.score for u in us if u.score is not None]
            out.append(f"• {name}: ko'rildi {len(us)}, joylandi {sum(u.state in POSTED for u in us)}" + (f", o'rtacha ball {sum(sc) / len(sc):.1f}" if sc else ""))
    else:
        out.append("\nManbalar: " + ", ".join(sources) + " — bu davrda yangi xabar bo'lmadi.")

    if posted:
        out.append("\nJoylangan postlar:\n" + "\n".join(_line(u, target) for u in posted[:25]) + (f"\n… yana {len(posted) - 25} ta" if len(posted) > 25 else ""))
    if review:
        out.append("\n🔎 Qo'lda ko'rib chiqing:\n" + "\n".join(f"• #{u.id} {u.channel_title}: {u.decision_reason}" for u in review[:20]))
    if errors:
        out.append("\n⚠️ Xatolar:\n" + "\n".join(f"• #{u.id}: {u.decision_reason} {(u.decision_detail or {}).get('error', '')[:80]}" for u in errors[:10]))

    if period.full_day and scored:
        ranked = sorted((u for u in units if u.score is not None), key=lambda u: u.score)
        best, worst = ranked[-3:][::-1], ranked[:3]
        out.append("\n🏆 Eng yaxshi: " + "; ".join(f"#{u.id} ({u.score:.1f}, {u.state})" for u in best))
        out.append("📉 Eng past: " + "; ".join(f"#{u.id} ({u.score:.1f}, {u.decision_reason or u.state})" for u in worst))

    out.append("\n🖥 Tizim:\n" + "\n".join(system_lines))
    return "\n".join(out)


async def system_lines(repo: Repository, connected: bool | None, dry_run: bool, paused: bool, disk_path: str = ".") -> list[str]:
    free_gb = shutil.disk_usage(disk_path).free / 1e9
    return [
        f"• Telethon: {'ulangan' if connected else ('uzilgan!' if connected is False else 'noma`lum')}",
        f"• Rejim: {'DRY-RUN' if dry_run else 'JONLI'}{' | ⏸ PAUZA' if paused else ''}",
        f"• Navbat: {await repo.count_pending()}",
        f"• Ketma-ket xatolar: {await repo.get_kv('consecutive_errors', '0')}",
        f"• Disk bo'sh: {free_gb:.1f} GB",
    ]
