import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import Base

target_metadata = Base.metadata
URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///data/hunter.db")


def _run(connection):
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


async def _online():
    engine = create_async_engine(URL)
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


asyncio.run(_online())
