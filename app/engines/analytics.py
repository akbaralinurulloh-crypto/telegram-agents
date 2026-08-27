from datetime import datetime, timedelta
from typing import List, Optional
from telethon import TelegramClient
from sqlalchemy import select, desc

from app.core.logging import logger
from app.core.database import get_db_session
from app.models.schema import Post, PostMetric


class AnalyticsEngine:
    """Telegramdagi postlarning ko'rishlar (views), reaksiyalar va ulashishlar statistikasini yig'uvchi engine."""

    @classmethod
    async def collect_post_metrics(cls, client: TelegramClient, limit: int = 20):
        async with get_db_session() as session:
            posts = (await session.execute(
                select(Post).where(Post.status == "ACTIVE").order_by(desc(Post.published_at)).limit(limit)
            )).scalars().all()

            for post in posts:
                try:
                    entity = await client.get_entity(post.target_channel)
                    messages = await client.get_messages(entity, ids=[post.target_message_id])
                    
                    if messages and messages[0]:
                        msg = messages[0]
                        views = getattr(msg, "views", 0) or 0
                        forwards = getattr(msg, "forwards", 0) or 0

                        # Reaksiyalarni sanash
                        reactions_count = 0
                        if getattr(msg, "reactions", None) and getattr(msg.reactions, "results", None):
                            reactions_count = sum(r.count for r in msg.reactions.results)

                        # Engagement rate hisoblash
                        eng_rate = 0.0
                        if views > 0:
                            eng_rate = round(((reactions_count + forwards) / float(views)) * 100, 2)

                        metric = PostMetric(
                            post_id=post.id,
                            checked_at=datetime.utcnow(),
                            views=views,
                            reactions_count=reactions_count,
                            forwards=forwards,
                            comments=0,
                            engagement_rate=eng_rate
                        )
                        session.add(metric)
                        logger.debug(f"📊 Post {post.target_message_id} statistikasi yangilandi: Views={views}, Reaksiyalar={reactions_count}, Eng={eng_rate}%")

                except Exception as e:
                    logger.warning(f"Post {post.target_message_id} statistikasini olishda xatolik: {e}")

            await session.commit()


analytics_engine = AnalyticsEngine()
