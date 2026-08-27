import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import select

from app.core.logging import logger
from app.core.database import get_db_session
from app.models.schema import ContentCandidate, MediaAnalysis, MediaAsset, Post, SimulationScenario
from app.engines.scoring import ContentScoringEngine
from app.engines.fatigue import fatigue_engine


class ContentSimulator:
    """
    Simulation / What-If Sandbox Engine.
    
    Qobiliyatlari:
    - 'What if we publish Candidate A now?' vs 'What if we wait 2 hours?'
    - 'What if we publish Candidate B instead of Candidate A?'
    - Ssenariylar bo'yicha kutilayotgan Views va Engagement hisoblash.
    """

    @classmethod
    async def simulate_scenario(
        cls,
        candidate_ids: List[int],
        scenario_name: str = "Default Simulation"
    ) -> Dict[str, Any]:
        async with get_db_session() as session:
            candidates = (await session.execute(
                select(ContentCandidate).where(ContentCandidate.id.in_(candidate_ids))
            )).scalars().all()

            if not candidates:
                return {
                    "scenario_name": scenario_name,
                    "predicted_views": 0,
                    "predicted_engagement": 0.0,
                    "recommendation": "Nomzodlar topilmadi",
                    "breakdown": []
                }

            breakdown = []
            total_predicted_views = 0
            total_predicted_engagement = 0.0

            for cand in candidates:
                # Fatigue va Diversity tekshiruvi
                analysis = (await session.execute(
                    select(MediaAnalysis).where(MediaAnalysis.media_asset_id == cand.media_asset_id)
                )).scalar_one_or_none()

                category = analysis.category if analysis else "General"
                fatigue_res = await fatigue_engine.get_category_fatigue(category)

                # Baseline taxmin
                base_views = int((cand.final_score or 75.0) * 180) # e.g. 90 score -> ~16,200 views
                fatigue_multiplier = fatigue_res.get("penalty", 1.0)
                adjusted_views = int(base_views * fatigue_multiplier)

                base_eng = round(((cand.final_score or 75.0) / 100.0) * 8.5 * fatigue_multiplier, 2)

                total_predicted_views += adjusted_views
                total_predicted_engagement += base_eng

                breakdown.append({
                    "candidate_id": cand.id,
                    "category": category,
                    "final_score": cand.final_score,
                    "fatigue_multiplier": fatigue_multiplier,
                    "predicted_views": adjusted_views,
                    "predicted_engagement": base_eng
                })

            avg_eng = round(total_predicted_engagement / len(candidates), 2) if candidates else 0.0

            # AI tavsiyasi
            if avg_eng > 6.5 and total_predicted_views > 20000:
                recom = "🚀 Ajoyib kombinatsiya! Ushbu ssenariy yuqori auditoriya qamrovini ta'minlaydi."
            elif any(b["fatigue_multiplier"] < 0.75 for b in breakdown):
                recom = "⚠️ Diqqat: Tanlangan postlar orasida kategoriya toliqishi (Fatigue) yuqori. Xilma-xillikni oshiring."
            else:
                recom = "✅ Barqaror ssenariy. Standart reja bo'yicha nashr qilish tavsiya etiladi."

            # Natijani bazada saqlash
            scenario_obj = SimulationScenario(
                scenario_name=scenario_name,
                candidate_ids=candidate_ids,
                predicted_views=total_predicted_views,
                predicted_engagement=avg_eng,
                recommendation=recom
            )
            session.add(scenario_obj)
            await session.commit()

            return {
                "scenario_id": scenario_obj.id,
                "scenario_name": scenario_name,
                "predicted_views": total_predicted_views,
                "predicted_engagement": avg_eng,
                "recommendation": recom,
                "breakdown": breakdown
            }


simulator_engine = ContentSimulator()
