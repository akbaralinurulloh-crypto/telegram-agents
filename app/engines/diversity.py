from typing import Dict, Any, List
from sqlalchemy import select, desc
from app.core.database import get_db_session
from app.models.schema import Post, MediaAnalysis, ContentCandidate, MediaAsset


class DiversityEngine:
    """Kontent xilma-xilligi va formatlar balansi engine."""

    @classmethod
    async def evaluate_diversity_fit(cls, category: str, media_type: str) -> float:
        """
        Ketma-ket bir xil kategoriya yoki bir xil format kelganda xilma-xillik koeffitsientini hisoblaydi.
        Qaytaradi: 0.5 dan 1.0 gacha ko'paytiruvchi
        """
        async with get_db_session() as session:
            query = (
                select(MediaAnalysis.category, MediaAsset.mime_type)
                .join(MediaAsset, MediaAnalysis.media_asset_id == MediaAsset.id)
                .join(ContentCandidate, ContentCandidate.media_asset_id == MediaAsset.id)
                .join(Post, Post.candidate_id == ContentCandidate.id)
                .order_by(desc(Post.published_at))
                .limit(3)
            )
            rows = (await session.execute(query)).all()

            if not rows:
                return 1.0

            multiplier = 1.0
            # Agar oxirgi post ham aynan shu kategoriya bo'lsa
            if rows[0][0] == category:
                multiplier *= 0.85
            # Agar oxirgi 2 ta post ham shu kategoriya bo'lsa
            if len(rows) >= 2 and rows[0][0] == category and rows[1][0] == category:
                multiplier *= 0.70

            return round(multiplier, 2)


diversity_engine = DiversityEngine()
