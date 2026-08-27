from datetime import datetime, timedelta
from typing import Dict, Any
from sqlalchemy import select, func, desc

from app.core.database import get_db_session
from app.models.schema import Post, MediaAnalysis, Category, ContentCandidate, MediaAsset
from app.core.logging import logger


class CategoryFatigueEngine:
    """Kategoriya toliqishi (Fatigue) va ketma-ketlikni nazorat qiluvchi engine."""

    @classmethod
    async def get_category_fatigue(cls, category_name: str) -> Dict[str, Any]:
        async with get_db_session() as session:
            # Oxirgi 10 ta e'lon qilingan postlar kategoriyasini olish
            query = (
                select(MediaAnalysis.category)
                .join(MediaAsset, MediaAnalysis.media_asset_id == MediaAsset.id)
                .join(ContentCandidate, ContentCandidate.media_asset_id == MediaAsset.id)
                .join(Post, Post.candidate_id == ContentCandidate.id)
                .order_by(desc(Post.published_at))
                .limit(10)
            )
            recent_categories = (await session.execute(query)).scalars().all()

            if not recent_categories:
                return {"category": category_name, "fatigue_score": 0.0, "status": "LOW", "penalty": 1.0, "recent_count": 0}

            # Oxirgi 10 postda necha marta chiqqani
            count = recent_categories.count(category_name)
            
            # Agar eng oxirgi post aynan shu toifadan bo'lsa
            last_was_same = (recent_categories[0] == category_name) if recent_categories else False
            
            # Fatigue score (0 dan 100 gacha)
            fatigue_score = (count / 10.0) * 100.0
            if last_was_same:
                fatigue_score += 25.0

            fatigue_score = min(100.0, fatigue_score)

            if fatigue_score >= 70.0:
                status = "HIGH"
                penalty = 0.70  # 30% jarima
            elif fatigue_score >= 40.0:
                status = "MEDIUM"
                penalty = 0.85  # 15% jarima
            else:
                status = "LOW"
                penalty = 1.0   # Jarimasiz

            return {
                "category": category_name,
                "fatigue_score": round(fatigue_score, 1),
                "status": status,
                "penalty": penalty,
                "recent_count": count
            }


fatigue_engine = CategoryFatigueEngine()
