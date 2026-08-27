import pytest
from app.engines.scoring import ContentScoringEngine
from app.engines.ai_provider import AnalysisSchema
from app.engines.quality import TechnicalQualityReport


def test_scoring_calculation_excellent():
    analysis = AnalysisSchema(
        category="Makkah",
        visual_quality=95,
        emotional_impact=90,
        relevance=95,
        uniqueness=90,
        freshness=90,
        information_value=85,
        risk_level="LOW",
        confidence=0.95,
        recommendation="CANDIDATE",
        reason="Ajoyib sifat"
    )
    tech = TechnicalQualityReport(
        score=90,
        width=1920,
        height=1080,
        is_hd=True
    )

    result = ContentScoringEngine.calculate_score(analysis, tech, source_trust_score=1.0)
    assert result["score"] >= 88.0
    assert result["grade"] in ["GOOD", "EXCELLENT"]


def test_scoring_calculation_reject():
    analysis = AnalysisSchema(
        category="Other",
        visual_quality=30,
        emotional_impact=20,
        relevance=10,
        uniqueness=20,
        freshness=30,
        information_value=10,
        risk_level="HIGH",
        confidence=0.5,
        recommendation="REJECT"
    )
    tech = TechnicalQualityReport(
        score=40,
        width=400,
        height=300
    )

    result = ContentScoringEngine.calculate_score(analysis, tech, source_trust_score=0.5)
    assert result["score"] < 50.0
    assert result["grade"] == "REJECT"
