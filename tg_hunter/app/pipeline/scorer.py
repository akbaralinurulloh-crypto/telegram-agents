from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from app.config import AppConfig
from app.llm.base import LLMClient, LLMError
from app.llm.prompts import load_prompt


class ScoringError(Exception):
    """LLM javobi yaroqsiz yoki chaqiruv muvaffaqiyatsiz: post baholanmaydi (fail-closed)."""


@dataclass
class ScoreResult:
    topic_fit: float
    quality: float
    audience_interest: float
    media_quality: float | None
    final_score: float
    passed: bool
    reason: str
    risks: list[str] = field(default_factory=list)


def _num(data: dict, key: str) -> float:
    v = data.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 10:
        raise ScoringError(f"{key!r} 0..10 oralig'ida raqam emas: {v!r}")
    return float(v)


def combine(cfg: AppConfig, topic_fit: float, quality: float, interest: float, media: float | None) -> float:
    """Og'irlikli o'rtacha. Media bo'lmasa, media og'irligi qolganlarga proporsional taqsimlanadi."""
    w = cfg.scoring.weights
    parts = [(w.topic_fit, topic_fit), (w.quality, quality), (w.audience_interest, interest)]
    if media is not None:
        parts.append((w.media_quality, media))
    return sum(wt * s for wt, s in parts) / sum(wt for wt, _ in parts)


async def score_unit(
    llm: LLMClient, cfg: AppConfig, text: str, images: Sequence[bytes] = (), has_media: bool | None = None
) -> ScoreResult:
    has_media = bool(images) if has_media is None else has_media
    system = load_prompt("scorer", topic=cfg.channel_topic.strip() or "(mavzu ta'rifi berilmagan)")
    user = f"POST MATNI:\n<<<\n{text or '(matn yo`q)'}\n>>>\nMedia bor: {'ha' if has_media else 'yo`q'}"
    try:
        data = await llm.generate_json(system=system, user=user, images=list(images)[: cfg.llm.max_images])
    except LLMError as exc:
        raise ScoringError(str(exc)) from exc
    topic, quality, interest = _num(data, "topic_fit"), _num(data, "quality"), _num(data, "audience_interest")
    media = _num(data, "media_quality") if has_media else None
    final = combine(cfg, topic, quality, interest, media)
    risks = data.get("risks")
    return ScoreResult(
        topic_fit=topic,
        quality=quality,
        audience_interest=interest,
        media_quality=media,
        final_score=round(final, 2),
        passed=final >= cfg.scoring.min_score - 1e-9,
        reason=str(data.get("reason", ""))[:300],
        risks=[str(r) for r in risks] if isinstance(risks, list) else [],
    )
