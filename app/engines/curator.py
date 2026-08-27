from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy import select, desc
from app.core.database import get_db_session
from app.models.schema import ContentCandidate, MediaAsset, MediaAnalysis, SourceMessage, Source
from app.engines.fatigue import fatigue_engine
from app.engines.diversity import diversity_engine
from app.core.config import settings
from app.core.logging import logger


class ContentCurator:
    """Barcha mavjud nomzodlar hovuzidan eng sarasini tanlab beruvchi Bosh Kurator."""

    @classmethod
    async def curate_candidate(cls, candidate_id: int) -> Dict[str, Any]:
        async with get_db_session() as session:
            candidate = await session.get(ContentCandidate, candidate_id)
            if not candidate:
                raise ValueError("Candidate topilmadi")

            asset = await session.get(MediaAsset, candidate.media_asset_id)
            analysis = (await session.execute(
                select(MediaAnalysis).where(MediaAnalysis.media_asset_id == asset.id)
            )).scalar_one_or_none()

            category = analysis.category if analysis else "General"
            media_type = "video" if (asset.mime_type and asset.mime_type.startswith("video/")) else "photo"

            # 1. Fatigue va Diversity koeffitsientlari
            fatigue_info = await fatigue_engine.get_category_fatigue(category)
            diversity_multiplier = await diversity_engine.evaluate_diversity_fit(category, media_type)
            fatigue_multiplier = fatigue_info["penalty"]

            # 2. Audience Fit (0.8 - 1.2 o'rtasida dinamik)
            audience_fit = 1.0
            if analysis and analysis.emotional_impact >= 80:
                audience_fit += 0.1
            if analysis and analysis.information_value >= 80:
                audience_fit += 0.05

            # 3. Yakuniy ball hisobi
            base_score = candidate.content_score
            final_score = base_score * audience_fit * diversity_multiplier * fatigue_multiplier
            final_score = round(max(0.0, min(100.0, final_score)), 1)

            # 4. Qaror izohi (Decision Explanation)
            reasons_positive = []
            reasons_penalty = []

            if analysis and analysis.visual_quality >= 80:
                reasons_positive.append("Yuqori vizual tiniqlik va sifat")
            if analysis and analysis.emotional_impact >= 80:
                reasons_positive.append("Kuchli ma'naviy va emotsional ta'sir")
            if analysis and analysis.uniqueness >= 80:
                reasons_positive.append("Noyob va kamyob kadr")

            if fatigue_multiplier < 1.0:
                reasons_penalty.append(f"Kategoriya toliqishi ({category} - oxirgi postlarda ko'p chiqdi: {fatigue_info['recent_count']} ta)")
            if diversity_multiplier < 1.0:
                reasons_penalty.append("Ketma-ket bir xil mavzu chiqishining oldini olish jarimasi")

            explanation = {
                "category": category,
                "base_score": base_score,
                "audience_fit": round(audience_fit, 2),
                "fatigue_multiplier": fatigue_multiplier,
                "diversity_multiplier": diversity_multiplier,
                "final_score": final_score,
                "strengths": reasons_positive,
                "penalties": reasons_penalty,
                "summary": f"Final ball: {final_score}/100. " + (
                    "Kanal balansi va auditoriya ehtiyojiga juda mos!" if final_score >= 80 else "Zaxirada saqlanadi."
                )
            }

            candidate.audience_fit = round(audience_fit * 100, 1)
            candidate.fatigue_penalty = round((1.0 - fatigue_multiplier) * 100, 1)
            candidate.diversity_penalty = round((1.0 - diversity_multiplier) * 100, 1)
            candidate.final_score = final_score
            candidate.ai_explanation = explanation

            min_threshold = float(getattr(settings, "MIN_QUALITY_SCORE", 6) * 10)
            if final_score >= min_threshold:
                candidate.status = "READY"
            else:
                candidate.status = "REJECTED"

            await session.commit()
            return explanation


curator_engine = ContentCurator()
