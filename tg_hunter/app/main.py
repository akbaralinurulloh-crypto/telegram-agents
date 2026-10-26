from __future__ import annotations

import asyncio
import signal

from aiogram import Bot

from app.bot_admin import AdminContext, build_dispatcher, is_dry_run, is_paused
from app.config import get_settings, load_app_config
from app.db.repository import Repository
from app.db.session import create_all, make_engine, make_sessionmaker
from app.llm.factory import build_llm
from app.media_telethon import TelethonMedia
from app.pipeline.publisher import AiogramPublisher
from app.pipeline.runner import Pipeline
from app.reports.scheduler import ReportService
from app.utils.logging import get_logger, setup_logging
from app.watcher.listener import Watcher, build_client


async def run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    log = get_logger("main")
    cfg = load_app_config(settings.config_path)
    settings.require_telegram()
    settings.require_bot()

    engine = make_engine(settings.database_url)
    await create_all(engine)  # prod: `alembic upgrade head` ham mumkin
    repo = Repository(make_sessionmaker(engine))

    client = build_client(settings, cfg)
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("Telethon session avtorizatsiyadan o'tmagan: `python -m scripts.login` ni ishga tushiring")

    bot = Bot(settings.bot_token)
    admin_id, target = settings.admin_id, settings.target_channel

    async def notify(text: str) -> None:
        await bot.send_message(admin_id, text[:4000])

    llm = build_llm(settings, cfg)
    pipeline = Pipeline(
        repo, llm, cfg, AiogramPublisher(bot), TelethonMedia(client),
        target=target, admin_id=admin_id, dry_run_default=settings.dry_run, notify=notify,
    )
    watcher = Watcher(client, repo, settings.source_channels, on_new_unit=pipeline.wake, notify=notify)
    await watcher.resolve_sources()
    watcher.register()

    async def status() -> str:
        return (
            f"Agent ishlayapti.\nRejim: {'DRY-RUN' if await is_dry_run(repo, settings.dry_run) else 'JONLI'}"
            f"{' | ⏸ PAUZA' if await is_paused(repo) else ''}\nTelethon: {'ulangan' if client.is_connected() else 'UZILGAN'}"
            f"\nNavbat: {await repo.count_pending()}\nManbalar: {len(watcher.source_ids)}\nLLM: {cfg.llm.provider}"
        )

    dp = build_dispatcher(admin_id, AdminContext(repo, settings.source_channels, target, status))
    reports = ReportService(
        repo, notify, slots=cfg.report_times, tz=cfg.timezone, target=target, sources=settings.source_channels,
        connected=client.is_connected, dry_run_default=settings.dry_run,
    )
    scheduler = reports.start()

    log.info("started", dry_run=settings.dry_run, sources=len(watcher.source_ids), provider=cfg.llm.provider)
    try:
        await notify(f"🟢 TG Hunter ishga tushdi.\n{await status()}\n\nBirinchi ishga tushirish DRY-RUN da: postlar kanalga emas, sizga ko'rsatiladi. Jonli rejim: /dryrun off")
    except Exception as exc:  # admin botga hali /start yozmagan bo'lishi mumkin
        log.warning("startup_notice_failed", error=str(exc)[:120], hint="Botga Telegramda /start yozing")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))

    tasks = [
        asyncio.create_task(pipeline.run_forever(), name="pipeline"),
        asyncio.create_task(dp.start_polling(bot, handle_signals=False), name="admin_bot"),
        asyncio.create_task(client.run_until_disconnected(), name="telethon"),
        asyncio.create_task(stop.wait(), name="stop"),
    ]
    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in done:
        if t.get_name() != "stop" and t.exception():
            log.error("task_crashed", task=t.get_name(), error=repr(t.exception()))

    log.info("shutting_down")
    pipeline.running = False
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    scheduler.shutdown(wait=False)
    await bot.session.close()
    await client.disconnect()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
