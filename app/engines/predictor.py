from datetime import datetime
from typing import Dict, Any, Tuple
from sqlalchemy import select, func, desc

from app.core.database import get_db_session
from app.models.schema import AIPrediction, PredictionEvaluation, Post, PostMetric, ContentCandidate, MediaAsset, MediaAnalysis
from app.core.logging import logger


class AIPredictorEngine:
    """Pre-publish kutilma ko'rishlar va Prediction vs Actual baholovchi engine."""

    @classmethod
    async def predict_for_candidate(cls, candidate_id: int) -> Tuple[int, int, float]:
        async with get_db_session() as session:
            # Tarixiy o'rtacha ko'rishlar sonini olish
            avg_views = (await session.execute(
                select(func.avg(PostMetric.views))
            )).scalar() or 500.0

            avg_eng = (await session.execute(
                select(func.avg(PostMetric.engagement_rate))
            )).scalar() or 6.5

            min_views = int(avg_views * 0.8)
            max_views = int(avg_views * 1.3)
            exp_eng = round(avg_eng * 1.1, 1)

            pred = AIPrediction(
                candidate_id=candidate_id,
                expected_views_min=min_views,
                expected_views_max=max_views,
                expected_engagement_rate=exp_eng,
                predicted_at=datetime.utcnow()
            )
            session.add(pred)
            await session.commit()
            return min_views, max_views, exp_eng

    @classmethod
    async def evaluate_accuracy(cls, post_id: int):
        async with get_db_session() as session:
            post = await session.get(Post, post_id)
            if not post:
                return

            pred = (await session.execute(
                select(AIPrediction).where(AIPrediction.candidate_id == post.candidate_id)
            )).scalar_one_or_none()

            latest_metric = (await session.execute(
                select(PostMetric).where(PostMetric.post_id == post.id).order_by(desc(PostMetric.checked_at)).limit(1)
            )).scalar_one_or_none()

            if pred and latest_metric:
                expected_mid = (pred.expected_views_min + pred.expected_views_max) / 2.0
                actual_views = latest_metric.views
                diff = abs(actual_views - expected_mid)
                accuracy = max(0.0, 1.0 - (diff / max(expected_mid, 1.0)))

                eval_obj = PredictionEvaluation(
                    post_id=post.id,
                    prediction_id=pred.id,
                    actual_views=actual_views,
                    actual_engagement=latest_metric.engagement_rate,
                    accuracy_score=round(accuracy, 2),
                    evaluation_notes=f"Kutilgan: {pred.expected_views_min}-{pred.expected_views_max}, Haqiqiy: {actual_views}",
                    created_at=datetime.utcnow()
                )
                session.add(eval_obj)
                await session.commit()


predictor_engine = AIPredictorEngine()
