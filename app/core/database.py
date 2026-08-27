from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings
from app.core.logging import logger
from app.models.schema import Base, Category, StrategyRule, Source

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Asinxron ma'lumotlar bazasi sessiyasini taqdim etuvchi generator."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Barcha jadvallarni initsializatsiya qiladi va boshlang'ich default ma'lumotlarni kiritadi."""
    logger.info("🛠 Ma'lumotlar bazasi jadvallari tekshirilmoqda va initsializatsiya qilinmoqda...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Boshlang'ich default toifalar va sozlamalarni kiritish
    async with get_db_session() as session:
        from sqlalchemy import select

        # 1. Standart kategoriyalar
        default_categories = [
            ("Makkah", "Makka Mukarrama va Haram ziyorati", 25.0),
            ("Madinah", "Madina Munavvara va Nabaviy masjid", 25.0),
            ("Spiritual", "Ma'naviy va Ilohiy fotolavhalar", 20.0),
            ("Educational", "Ziyorat qoidalari va foydali ma'lumotlar", 15.0),
            ("Human Story", "Ziyoratchilar hissiyotlari va voqealar", 15.0),
        ]
        for name, display, target_pct in default_categories:
            res = await session.execute(select(Category).where(Category.name == name))
            if not res.scalar_one_or_none():
                session.add(Category(name=name, display_name=display, target_percentage=target_pct))

        # 2. Boshlang'ich manbalarni ro'yxatga kiritish
        for ch in settings.SOURCE_CHANNELS:
            res = await session.execute(select(Source).where(Source.username == ch))
            if not res.scalar_one_or_none():
                session.add(Source(username=ch, title=ch, status="ACTIVE", priority=3))

        # 3. Default strategik qoidalar
        default_rules = {
            "score_weights": {
                "visual_quality": 0.25,
                "emotional_impact": 0.20,
                "relevance": 0.15,
                "uniqueness": 0.15,
                "freshness": 0.10,
                "information_value": 0.10,
                "source_reliability": 0.05
            },
            "posting_limits": {
                "min_interval_minutes": settings.MIN_POST_INTERVAL_MINUTES,
                "max_daily_posts": settings.MAX_DAILY_POSTS,
                "active_start_hour": settings.ACTIVE_HOURS_START,
                "active_end_hour": settings.ACTIVE_HOURS_END
            }
        }
        for key, val in default_rules.items():
            res = await session.execute(select(StrategyRule).where(StrategyRule.key == key))
            if not res.scalar_one_or_none():
                session.add(StrategyRule(key=key, value=val, description=f"Default rule for {key}"))

        await session.commit()
    logger.info("✅ Ma'lumotlar bazasi va default ma'lumotlar muvaffaqiyatli tayyorlandi.")
