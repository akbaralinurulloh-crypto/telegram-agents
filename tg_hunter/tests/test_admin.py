import pytest

from app.bot_admin import AdminContext, handle_command, is_dry_run, is_paused
from app.db.repository import NormalizedUnit
from datetime import datetime, timezone


@pytest.fixture
def ctx(repo):
    async def status():
        return "status-ok"

    return AdminContext(repo, ["@a", "@b"], "@target", status)


async def test_pause_resume(ctx):
    assert not await is_paused(ctx.repo)
    assert "Pauza" in await handle_command("/pause", [], ctx)
    assert await is_paused(ctx.repo)
    await ctx.repo.set_kv("consecutive_errors", "4")
    await handle_command("/resume", [], ctx)
    assert not await is_paused(ctx.repo) and await ctx.repo.get_kv("consecutive_errors") == "0"


async def test_dryrun_defaults_on_and_toggles(ctx):
    assert await is_dry_run(ctx.repo, default=True)
    out = await handle_command("/dryrun", ["off"], ctx)
    assert "JONLI" in out and not await is_dry_run(ctx.repo)
    await handle_command("/dryrun", ["on"], ctx)
    assert await is_dry_run(ctx.repo, default=False)
    assert "Foydalanish" in await handle_command("/dryrun", ["maybe"], ctx)


async def test_sources_status_help_unknown(ctx):
    assert "@a" in await handle_command("/sources", [], ctx) and "@target" in await handle_command("/sources", [], ctx)
    assert await handle_command("/status", [], ctx) == "status-ok"
    assert "/pause" in await handle_command("/help", [], ctx)
    assert "Noma'lum" in await handle_command("/xyz", [], ctx)
    assert await handle_command("/status@my_bot", [], ctx) == "status-ok"


async def test_last(ctx):
    assert "yo'q" in await handle_command("/last", ["5"], ctx)
    u, _ = await ctx.repo.add_unit(NormalizedUnit(-1, "Src", [1], None, "Salom dunyo", [], datetime(2026, 1, 1, tzinfo=timezone.utc)))
    await ctx.repo.record_decision(u.id, "rejected", "low_score", score=5.5)
    out = await handle_command("/last", [], ctx)
    assert "rejected/low_score" in out and "ball=5.5" in out
