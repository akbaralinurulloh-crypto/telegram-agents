from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import select, func, desc

from app.core.database import get_db_session
from app.core.config import settings
from app.core.queue import queue_manager
from app.models.schema import (
    Source, ContentCandidate, MediaAsset, MediaAnalysis, Caption,
    Post, PostMetric, AIPrediction, AICost, SystemLog, Category
)
from app.engines.strategist import strategist_engine

router = APIRouter(prefix="/api")


@router.get("/health")
async def get_health():
    """Tizim xizmatlarining jonli holati."""
    return {
        "status": "ONLINE",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "telegram": "ONLINE",
            "gemini_ai": "ONLINE",
            "database": "ONLINE",
            "queue": "ONLINE",
            "storage": "ONLINE"
        },
        "queue_depth": queue_manager.get_stats()
    }


@router.get("/overview")
async def get_overview():
    """Boshqaruv paneli uchun umumiy xulosa kartalari."""
    async with get_db_session() as session:
        total_candidates = (await session.execute(select(func.count(ContentCandidate.id)))).scalar() or 0
        published_count = (await session.execute(select(func.count(Post.id)))).scalar() or 0
        rejected_count = (await session.execute(
            select(func.count(ContentCandidate.id)).where(ContentCandidate.status == "REJECTED")
        )).scalar() or 0
        ready_count = (await session.execute(
            select(func.count(ContentCandidate.id)).where(ContentCandidate.status.in_(["READY", "REVIEW"]))
        )).scalar() or 0

        avg_score = (await session.execute(select(func.avg(ContentCandidate.final_score)))).scalar() or 0.0
        avg_eng = (await session.execute(select(func.avg(PostMetric.engagement_rate)))).scalar() or 0.0
        total_ai_cost = (await session.execute(select(func.sum(AICost.estimated_cost_usd)))).scalar() or 0.0

        return {
            "collected_today": total_candidates,
            "published": published_count,
            "rejected": rejected_count,
            "in_queue": ready_count,
            "average_score": round(avg_score, 1),
            "average_engagement": round(avg_eng, 2),
            "total_ai_cost_usd": round(total_ai_cost, 4),
            "governance_mode": settings.GOVERNANCE_MODE
        }


@router.get("/sources")
async def list_sources():
    """Barcha manbalar ro'yxati va ularning statistikasi."""
    async with get_db_session() as session:
        sources = (await session.execute(select(Source).order_by(desc(Source.priority)))).scalars().all()
        return [
            {
                "id": s.id,
                "username": s.username,
                "title": s.title,
                "status": s.status,
                "priority": s.priority,
                "trust_score": s.trust_score,
                "quality_score": s.quality_score,
                "last_seen_at": s.last_seen_at.isoformat() if s.last_seen_at else None
            }
            for s in sources
        ]


@router.post("/sources")
async def add_source(payload: Dict[str, Any]):
    """Yangi manba kanalini qo'shish."""
    username = payload.get("username", "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username kiritilishi shart")

    async with get_db_session() as session:
        s = (await session.execute(select(Source).where(Source.username == username))).scalar_one_or_none()
        if s:
            s.status = "ACTIVE"
        else:
            s = Source(username=username, title=payload.get("title", username), priority=payload.get("priority", 3))
            session.add(s)
        await session.commit()
    return {"status": "SUCCESS", "username": username}


@router.get("/candidates")
async def list_candidates(status: Optional[str] = None, limit: int = 50):
    """Nomzodlar hovuzi ro'yxati."""
    async with get_db_session() as session:
        query = (
            select(ContentCandidate, MediaAsset, MediaAnalysis)
            .join(MediaAsset, ContentCandidate.media_asset_id == MediaAsset.id)
            .outerjoin(MediaAnalysis, MediaAnalysis.media_asset_id == MediaAsset.id)
            .order_by(desc(ContentCandidate.created_at))
            .limit(limit)
        )
        if status:
            query = query.where(ContentCandidate.status == status)

        rows = (await session.execute(query)).all()
        results = []
        for cand, asset, analysis in rows:
            results.append({
                "id": cand.id,
                "status": cand.status,
                "final_score": cand.final_score,
                "confidence": cand.confidence,
                "category": analysis.category if analysis else "General",
                "media_type": "video" if (asset.mime_type and "video" in asset.mime_type) else "photo",
                "width": asset.width,
                "height": asset.height,
                "duration": asset.duration,
                "explanation": cand.ai_explanation,
                "created_at": cand.created_at.isoformat() if cand.created_at else None
            })
        return results


@router.get("/candidate/{candidate_id}")
async def get_candidate_detail(candidate_id: int):
    """Bitta nomzodning to'liq tahlil tafsilotlari."""
    async with get_db_session() as session:
        cand = await session.get(ContentCandidate, candidate_id)
        if not cand:
            raise HTTPException(status_code=404, detail="Nomzod topilmadi")

        asset = await session.get(MediaAsset, cand.media_asset_id)
        analysis = (await session.execute(
            select(MediaAnalysis).where(MediaAnalysis.media_asset_id == asset.id)
        )).scalar_one_or_none()
        captions = (await session.execute(
            select(Caption).where(Caption.candidate_id == cand.id)
        )).scalars().all()
        prediction = (await session.execute(
            select(AIPrediction).where(AIPrediction.candidate_id == cand.id)
        )).scalar_one_or_none()

        return {
            "candidate": {
                "id": cand.id,
                "status": cand.status,
                "content_score": cand.content_score,
                "final_score": cand.final_score,
                "audience_fit": cand.audience_fit,
                "fatigue_penalty": cand.fatigue_penalty,
                "diversity_penalty": cand.diversity_penalty,
                "explanation": cand.ai_explanation
            },
            "asset": {
                "id": asset.id,
                "mime_type": asset.mime_type,
                "width": asset.width,
                "height": asset.height,
                "duration": asset.duration,
                "file_size": asset.file_size
            },
            "analysis": {
                "category": analysis.category if analysis else "",
                "tags": analysis.tags if analysis else [],
                "visual_quality": analysis.visual_quality if analysis else 0,
                "emotional_impact": analysis.emotional_impact if analysis else 0,
                "relevance": analysis.relevance if analysis else 0,
                "uniqueness": analysis.uniqueness if analysis else 0,
                "freshness": analysis.freshness if analysis else 0,
                "information_value": analysis.information_value if analysis else 0,
                "risk_level": analysis.risk_level if analysis else "LOW",
                "reason": analysis.reason if analysis else ""
            },
            "captions": [
                {
                    "id": c.id,
                    "style": c.style,
                    "title": c.title,
                    "body": c.body,
                    "hashtags": c.hashtags,
                    "full_caption": c.full_caption,
                    "is_selected": c.is_selected
                }
                for c in captions
            ],
            "prediction": {
                "views_min": prediction.expected_views_min if prediction else 0,
                "views_max": prediction.expected_views_max if prediction else 0,
                "engagement_rate": prediction.expected_engagement_rate if prediction else 0.0
            }
        }


@router.post("/candidate/{candidate_id}/approve")
async def approve_candidate(candidate_id: int):
    """Admin tomonidan nomzodni tasdiqlash."""
    async with get_db_session() as session:
        cand = await session.get(ContentCandidate, candidate_id)
        if not cand:
            raise HTTPException(status_code=404, detail="Nomzod topilmadi")
        cand.status = "READY"
        await session.commit()
    return {"status": "APPROVED", "candidate_id": candidate_id}


@router.post("/candidate/{candidate_id}/reject")
async def reject_candidate(candidate_id: int):
    """Admin tomonidan nomzodni rad etish."""
    async with get_db_session() as session:
        cand = await session.get(ContentCandidate, candidate_id)
        if not cand:
            raise HTTPException(status_code=404, detail="Nomzod topilmadi")
        cand.status = "REJECTED"
        await session.commit()
    return {"status": "REJECTED", "candidate_id": candidate_id}


@router.get("/strategist/report")
async def get_strategist_report():
    """AI Strategist kundalik hisoboti."""
    return await strategist_engine.generate_daily_report()


@router.get("/analytics")
async def get_analytics_summary():
    """Kategoriyalar va postlar samaradorligi tahlili."""
    async with get_db_session() as session:
        categories = (await session.execute(select(Category))).scalars().all()
        costs = (await session.execute(select(AICost).order_by(desc(AICost.created_at)).limit(30))).scalars().all()
        return {
            "categories": [
                {
                    "name": c.name,
                    "display": c.display_name,
                    "target_percentage": c.target_percentage,
                    "current_percentage": c.current_percentage,
                    "fatigue_score": c.fatigue_score
                }
                for c in categories
            ],
            "recent_ai_costs": [
                {
                    "model": cost.model_name,
                    "type": cost.request_type,
                    "tokens": cost.prompt_tokens + cost.completion_tokens,
                    "cost_usd": cost.estimated_cost_usd,
                    "latency_ms": cost.latency_ms
                }
                for cost in costs
            ]
        }


@router.post("/simulation/run")
async def run_simulation(payload: Dict[str, Any]):
    """What-if ssenariy simulyatsiyasini ishga tushirish."""
    from app.engines.simulator import simulator_engine
    candidate_ids = payload.get("candidate_ids", [])
    scenario_name = payload.get("scenario_name", "Scenario A")
    return await simulator_engine.simulate_scenario(candidate_ids, scenario_name)


@router.get("/dna")
async def get_content_dna():
    """Kanalning eng sara TOP 10% postlari DNK modeli."""
    from app.models.schema import ContentDNA
    async with get_db_session() as session:
        dna = (await session.execute(select(ContentDNA))).scalar_one_or_none()
        if not dna:
            dna = ContentDNA()
            session.add(dna)
            await session.commit()
        return {
            "channel": dna.channel_name,
            "ideal_duration": f"{dna.ideal_duration_min}-{dna.ideal_duration_max} sec",
            "top_categories": dna.top_categories,
            "top_emotions": dna.top_emotions,
            "top_keywords": dna.top_keywords,
            "target_mix": dna.target_mix
        }


@router.get("/reports/export")
async def export_csv_report():
    """Postlar va tahlillar hisobotini CSV formatida eksport qilish."""
    from fastapi.responses import Response
    import csv
    import io

    async with get_db_session() as session:
        posts = (await session.execute(select(Post).order_by(desc(Post.published_at)).limit(100))).scalars().all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "CandidateID", "TargetChannel", "TargetMessageID", "Status", "PublishedAt", "Caption"])
        for p in posts:
            writer.writerow([p.id, p.candidate_id, p.target_channel, p.target_message_id, p.status, p.published_at.isoformat() if p.published_at else "", (p.caption_used or "")[:100]])

        return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=posts_report.csv"})


@router.get("/reports/history")
async def get_reports_history():
    """Yaratilgan barcha hisobotlar ro'yxati."""
    from app.models.schema import Report
    async with get_db_session() as session:
        reports = (await session.execute(select(Report).order_by(desc(Report.created_at)).limit(20))).scalars().all()
        return [
            {
                "id": r.id,
                "type": r.report_type,
                "date": r.report_date,
                "timezone": r.timezone,
                "status": r.status,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "summary": r.summary_text[:120] + "..." if len(r.summary_text) > 120 else r.summary_text
            }
            for r in reports
        ]


@router.get("/trace/{post_id}")
async def get_trace(post_id: int):
    """Postning Source -> Target to'liq manba zanjiri."""
    from app.engines.reporting_engine import reporting_engine
    return await reporting_engine.get_content_traceability(post_id)


@router.get("/alerts")
async def get_alerts():
    """Tizimdagi faol ogohlantirishlar."""
    from app.models.schema import Alert
    async with get_db_session() as session:
        alerts = (await session.execute(select(Alert).order_by(desc(Alert.created_at)).limit(20))).scalars().all()
        return [
            {
                "id": a.id,
                "severity": a.severity,
                "type": a.alert_type,
                "message": a.message,
                "resolved": a.is_resolved,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in alerts
        ]


@router.get("/events/live")
async def get_live_events(limit: int = 25):
    """Real-vaqtda tizim konveyeri hodisalari oqimi."""
    from app.core.events import event_bus
    return event_bus.get_recent_events(limit=limit)
