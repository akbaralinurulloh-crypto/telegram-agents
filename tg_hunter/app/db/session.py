from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.db.models import Base


def make_engine(url: str) -> AsyncEngine:
    if url.startswith("sqlite"):
        db_path = url.split("///", 1)[-1]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(url)
    if url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def _pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return engine


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_all(engine: AsyncEngine) -> None:
    """Dev uchun. Productionda `alembic upgrade head` ishlatiladi."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
