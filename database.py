import aiosqlite
from datetime import datetime
from app.core.config import settings
from app.core.database import init_db as app_init_db, get_db_session
from app.models.schema import LegacyProcessedMessage
from sqlalchemy import select, func

DATABASE_PATH = settings.BASE_DIR / "agent_database.sqlite"


async def init_db():
    """Barcha jadvallarni va orqaga moslikni initsializatsiya qilish."""
    await app_init_db()


async def is_message_processed(source_channel: str, source_message_id: int) -> bool:
    """Xabar avval tekshirilganmi (ERROR bo'lmagan)? (Yangi va eski jadvallar orqali)."""
    async with get_db_session() as session:
        query = select(LegacyProcessedMessage).where(
            LegacyProcessedMessage.source_channel == source_channel,
            LegacyProcessedMessage.source_message_id == source_message_id,
            LegacyProcessedMessage.status != "ERROR"
        )
        res = await session.execute(query)
        return res.scalar_one_or_none() is not None


async def save_processed_message(
    source_channel: str,
    source_message_id: int,
    media_type: str,
    status: str,
    quality_score: int = 0,
    reason: str = "",
    target_message_id: int | None = None,
    original_caption: str | None = None,
    enhanced_caption: str | None = None
):
    """Qayta ishlangan xabar natijasini bazaga yozib qo'yish (orqaga moslik bilan)."""
    async with get_db_session() as session:
        # Avval mavjud bo'lsa yangilash, bo'lmasa yaratish
        query = select(LegacyProcessedMessage).where(
            LegacyProcessedMessage.source_channel == source_channel,
            LegacyProcessedMessage.source_message_id == source_message_id
        )
        res = await session.execute(query)
        obj = res.scalar_one_or_none()
        if not obj:
            obj = LegacyProcessedMessage(
                source_channel=source_channel,
                source_message_id=source_message_id
            )
            session.add(obj)
        
        obj.media_type = media_type
        obj.status = status
        obj.quality_score = quality_score
        obj.reason = reason
        obj.target_message_id = target_message_id
        obj.original_caption = original_caption
        obj.enhanced_caption = enhanced_caption
        obj.created_at = datetime.utcnow()
        await session.commit()


async def get_stats() -> dict:
    """Agent faoliyati statistikasi."""
    async with get_db_session() as session:
        from app.models.schema import Post, ContentCandidate
        total_cand = (await session.execute(select(func.count(ContentCandidate.id)))).scalar() or 0
        total_posts = (await session.execute(select(func.count(Post.id)))).scalar() or 0
        rejected_cand = (await session.execute(
            select(func.count(ContentCandidate.id)).where(ContentCandidate.status == "REJECTED")
        )).scalar() or 0

        legacy_total = (await session.execute(select(func.count(LegacyProcessedMessage.id)))).scalar() or 0
        legacy_posted = (await session.execute(
            select(func.count(LegacyProcessedMessage.id)).where(LegacyProcessedMessage.status == "POSTED")
        )).scalar() or 0

        return {
            "total_candidates": total_cand,
            "published_posts": total_posts,
            "rejected_candidates": rejected_cand,
            "legacy_processed": legacy_total,
            "legacy_posted": legacy_posted
        }
