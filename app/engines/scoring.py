from typing import Dict, Any
from app.engines.ai_provider import AnalysisSchema
from app.engines.quality import TechnicalQualityReport
from app.core.logging import logger


class ContentScoringEngine:
    """Ko'p faktorli vaznli ball hisoblagich (Content Scoring Engine)."""

    DEFAULT_WEIGHTS = {
        "visual_quality": 0.25,
        "emotional_impact": 0.20,
        "relevance": 0.15,
        "uniqueness": 0.15,
        "freshness": 0.10,
        "information_value": 0.10,
        "source_reliability": 0.05
    }

    @classmethod
    def calculate_score(
        cls,
        analysis: AnalysisSchema,
        tech_quality: TechnicalQualityReport,
        source_trust_score: float = 1.0,
        custom_weights: Dict[str, float] = None
    ) -> Dict[str, Any]:
        weights = custom_weights or cls.DEFAULT_WEIGHTS

        # Vizual sifat = (AI Vision bahosi * 0.6) + (Texnik piksellar bahosi * 0.4)
        combined_visual = (analysis.visual_quality * 0.6) + (tech_quality.score * 0.4)

        score = (
            (combined_visual * weights["visual_quality"]) +
            (analysis.emotional_impact * weights["emotional_impact"]) +
            (analysis.relevance * weights["relevance"]) +
            (analysis.uniqueness * weights["uniqueness"]) +
            (analysis.freshness * weights["freshness"]) +
            (analysis.information_value * weights["information_value"]) +
            ((source_trust_score * 100) * weights["source_reliability"])
        )

        score = round(max(0.0, min(100.0, score)), 1)

        # Daraja (Grade)
        if score >= 90:
            grade = "EXCELLENT"
        elif score >= 80:
            grade = "GOOD"
        elif score >= 70:
            grade = "RESERVE"
        elif score >= 60:
            grade = "LOW"
        else:
            grade = "REJECT"

        return {
            "score": score,
            "grade": grade,
            "components": {
                "combined_visual": round(combined_visual, 1),
                "emotional_impact": analysis.emotional_impact,
                "relevance": analysis.relevance,
                "uniqueness": analysis.uniqueness,
                "freshness": analysis.freshness,
                "information_value": analysis.information_value,
                "source_reliability": round(source_trust_score * 100, 1)
            }
        }


scoring_engine = ContentScoringEngine()
