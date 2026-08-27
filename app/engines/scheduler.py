from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, desc
from app.core.config import settings
from app.core.database import get_db_session
from app.models.schema import Post, Schedule, ContentCandidate
from app.core.logging import logger


class SmartScheduler:
    """Optimal post joylash vaqti va oraliq intervallarni hisoblovchi Smart Scheduler."""

    @classmethod
    async def get_next_optimal_time(cls, is_breaking: bool = False) -> datetime:
        now = datetime.utcnow()
        if is_breaking:
            return now

        async with get_db_session() as session:
            # Oxirgi rejalashtirilgan yoki e'lon qilingan post vaqtini olish
            last_schedule = (await session.execute(
                select(Schedule.scheduled_time).order_by(desc(Schedule.scheduled_time)).limit(1)
            )).scalar_one_or_none()

            last_post = (await session.execute(
                select(Post.published_at).order_by(desc(Post.published_at)).limit(1)
            )).scalar_one_or_none()

            latest_time = max(filter(None, [last_schedule, last_post, now]))

            # Minimal interval qo'shish (masalan 45 daqiqa)
            target_time = latest_time + timedelta(minutes=settings.MIN_POST_INTERVAL_MINUTES)

            # Agar target_time o'tmishda qolib ketgan bo'lsa
            if target_time < now:
                target_time = now

            # Aktiv soatlar nazorati (Toshkent vaqti UTC+5 bo'yicha)
            tashkent_hour = (target_time.hour + 5) % 24
            if tashkent_hour < settings.ACTIVE_HOURS_START:
                # Ertalabki soat 7:30 ga ko'chirish
                hours_to_add = (settings.ACTIVE_HOURS_START - tashkent_hour)
                target_time += timedelta(hours=hours_to_add, minutes=30)
            elif tashkent_hour >= settings.ACTIVE_HOURS_END:
                # Ertangi tongga ko'chirish
                target_time += timedelta(hours=8)

            return target_time


scheduler_engine = SmartScheduler()
