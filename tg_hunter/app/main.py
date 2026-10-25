from __future__ import annotations

import asyncio
import signal

from app.config import get_settings, load_app_config
from app.db.repository import Repository
from app.db.session import create_all, make_engine, make_sessionmaker
from app.utils.logging import get_logger, setup_logging
from app.watcher.listener import Watcher, build_client


async def run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    log = get_logger("main")
    cfg = load_app_config(settings.config_path)
    settings.require_telegram()

    engine = make_engine(settings.database_url)
    await create_all(engine)  # TODO(stage 7): alembic upgrade head
    repo = Repository(make_sessionmaker(engine))

    client = build_client(settings, cfg)
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("Telethon session avtorizatsiyadan o'tmagan: `python -m scripts.login` ni ishga tushiring")

    watcher = Watcher(client, repo, settings.source_channels)
    await watcher.resolve_sources()
    watcher.register()
    log.info("started", mode="read_only", dry_run=settings.dry_run, sources=len(watcher.source_ids))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    disconnected = asyncio.ensure_future(client.run_until_disconnected())
    stopper = asyncio.ensure_future(stop.wait())
    await asyncio.wait({disconnected, stopper}, return_when=asyncio.FIRST_COMPLETED)

    log.info("shutting_down")
    await client.disconnect()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
