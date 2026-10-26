"""Admin bot: faqat ADMIN_ID buyruq bera oladi. Mantiq `handle_command` da (aiogram'dan mustaqil, testlanadi)."""
from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

from app.db.repository import Repository
from app.utils.logging import get_logger

log = get_logger("admin")

PAUSED, DRYRUN = "paused", "dry_run"


@dataclass
class AdminContext:
    repo: Repository
    sources: list[str]
    target: str
    status_fn: "callable"  # async () -> str


async def is_paused(repo: Repository) -> bool:
    return (await repo.get_kv(PAUSED, "0")) == "1"


async def is_dry_run(repo: Repository, default: bool = True) -> bool:
    v = await repo.get_kv(DRYRUN)
    return default if v is None else v == "1"


async def handle_command(cmd: str, args: list[str], ctx: AdminContext) -> str:
    cmd = cmd.lstrip("/").split("@")[0].lower()
    if cmd in ("start", "help"):
        return "Buyruqlar: /status, /pause, /resume, /dryrun on|off, /sources, /last [N]"
    if cmd == "status":
        return await ctx.status_fn()
    if cmd == "pause":
        await ctx.repo.set_kv(PAUSED, "1")
        await ctx.repo.audit("admin_pause")
        return "⏸ Pauza: yangi xabarlar qayta ishlanmaydi (o'qish davom etadi)."
    if cmd == "resume":
        await ctx.repo.set_kv(PAUSED, "0")
        await ctx.repo.set_kv("consecutive_errors", "0")
        await ctx.repo.audit("admin_resume")
        return "▶️ Davom etdi."
    if cmd == "dryrun":
        if not args or args[0].lower() not in ("on", "off"):
            return f"Hozir DRY-RUN: {'yoqiq' if await is_dry_run(ctx.repo) else 'o`chiq (JONLI)'}.\nFoydalanish: /dryrun on|off"
        on = args[0].lower() == "on"
        await ctx.repo.set_kv(DRYRUN, "1" if on else "0")
        await ctx.repo.audit("admin_dryrun", on=on)
        return "🧪 DRY-RUN yoqildi: kanalga joylanmaydi, faqat sizga ko'rsatiladi." if on else f"🔴 JONLI rejim: postlar {ctx.target} ga joylanadi."
    if cmd == "sources":
        return "Manba kanallar:\n" + "\n".join(f"• {s}" for s in ctx.sources) + f"\nMaqsad: {ctx.target}"
    if cmd == "last":
        n = int(args[0]) if args and args[0].isdigit() else 10
        rows = await ctx.repo.last_units(max(1, min(n, 30)))
        if not rows:
            return "Hali xabar yo'q."
        return "\n".join(
            f"#{u.id} {u.state}{'/' + u.decision_reason if u.decision_reason else ''}"
            f"{f' ball={u.score:.1f}' if u.score is not None else ''} — {u.channel_title}: {(u.text or '(media)')[:40]!r}"
            for u in rows
        )
    return "Noma'lum buyruq. /help"


def build_dispatcher(admin_id: int, ctx: AdminContext) -> Dispatcher:
    dp = Dispatcher()
    only_admin = F.from_user.id == admin_id

    @dp.message(Command("start", "help", "status", "pause", "resume", "dryrun", "sources", "last"), only_admin)
    async def _cmd(message: Message):
        text = (message.text or "").split()
        await message.answer(await handle_command(text[0], text[1:], ctx))

    @dp.message()
    async def _other(message: Message):
        if message.from_user and message.from_user.id != admin_id:
            log.warning("unauthorized_message", user_id=message.from_user.id)

    return dp
