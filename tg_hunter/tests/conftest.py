import pytest_asyncio

from app.db.repository import Repository
from app.db.session import create_all, make_engine, make_sessionmaker


@pytest_asyncio.fixture
async def repo():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    yield Repository(make_sessionmaker(engine))
    await engine.dispose()
