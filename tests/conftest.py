import pytest
from app.core.database import init_db


@pytest.fixture(autouse=True, scope="session")
async def setup_test_database():
    await init_db()
