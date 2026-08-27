import json
from datetime import datetime
from typing import Optional, List, Any
from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Boolean, DateTime, Text, ForeignKey, JSON
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Source(Base):
    """Manba Telegram kanallari reestri."""
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(128), unique=True, index=True, nullable=False)
    title = Column(String(256), default="")
    telegram_id = Column(Integer, nullable=True, index=True)
    type = Column(String(32), default="CHANNEL")  # CHANNEL, GROUP, CHAT
    status = Column(String(32), default="ACTIVE")  # ACTIVE, PAUSED, BLOCKED, ERROR
    priority = Column(Integer, default=1)          # 1 - past, 5 - yuqori
    trust_score = Column(Float, default=1.0)       # 0.0 dan 1.0 gacha
    quality_score = Column(Float, default=7.0)     # Tarixiy o'rtacha sifat
    performance_score = Column(Float, default=0.0) # Ko'rishlar va engagement indeksi
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)

    messages = relationship("SourceMessage", back_populates="source", cascade="all, delete-orphan")


class SourceMessage(Base):
    """Manbalardan kelgan har bir post jurnali."""
    __tablename__ = "source_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False, index=True)
    source_message_id = Column(Integer, nullable=False, index=True)
    media_type = Column(String(32), default="text")  # photo, video, document, text
    raw_text = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    source = relationship("Source", back_populates="messages")
    media_asset = relationship("MediaAsset", back_populates="source_message", uselist=False)


class MediaAsset(Base):
    """Media fayllar ombori va metama'lumotlari."""
    __tablename__ = "media_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_message_id = Column(Integer, ForeignKey("source_messages.id"), nullable=True, index=True)
    storage_provider = Column(String(32), default="local")  # local, s3
    storage_key = Column(String(512), nullable=False)
    local_path = Column(String(512), default="")
    mime_type = Column(String(64), default="")
    file_size = Column(Integer, default=0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    duration = Column(Float, default=0.0)
    sha256_hash = Column(String(64), index=True)
    phash = Column(String(64), index=True)
    dhash = Column(String(64), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    source_message = relationship("SourceMessage", back_populates="media_asset")
    analysis = relationship("MediaAnalysis", back_populates="media_asset", uselist=False)
    candidate = relationship("ContentCandidate", back_populates="media_asset", uselist=False)


class MediaAnalysis(Base):
    """Gemini Vision ko'p o'lchovli structured AI tahlili."""
    __tablename__ = "media_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    media_asset_id = Column(Integer, ForeignKey("media_assets.id"), nullable=False, index=True)
    category = Column(String(64), default="General", index=True)
    sub_category = Column(String(64), default="")
    tags = Column(JSON, default=list)
    visual_quality = Column(Integer, default=50)     # 0-100
    emotional_impact = Column(Integer, default=50)   # 0-100
    relevance = Column(Integer, default=50)          # 0-100
    uniqueness = Column(Integer, default=50)         # 0-100
    freshness = Column(Integer, default=50)          # 0-100
    information_value = Column(Integer, default=50)  # 0-100
    risk_level = Column(String(32), default="LOW")   # LOW, MEDIUM, HIGH
    confidence = Column(Float, default=0.8)          # 0.0 - 1.0
    recommendation = Column(String(32), default="CANDIDATE") # CANDIDATE, REJECT, REVIEW
    reason = Column(Text, default="")
    raw_ai_response = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    media_asset = relationship("MediaAsset", back_populates="analysis")


class DuplicateMatch(Base):
    """Dublikatlar va o'xshashliklar indeksi."""
    __tablename__ = "duplicate_matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    media_asset_id = Column(Integer, ForeignKey("media_assets.id"), nullable=False)
    matched_media_id = Column(Integer, ForeignKey("media_assets.id"), nullable=False)
    match_type = Column(String(32), default="PHASH")  # EXACT_SHA256, PHASH, DHASH, EMBEDDING
    similarity_score = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Category(Base):
    """Dinamik kontent toifalari va toliqish (fatigue) ko'rsatkichlari."""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, index=True, nullable=False)
    display_name = Column(String(128), default="")
    target_percentage = Column(Float, default=20.0)  # Ideal ulush (%)
    current_percentage = Column(Float, default=20.0) # Haqiqiy ulush (%)
    fatigue_score = Column(Float, default=0.0)       # 0 dan 100 gacha
    cooldown_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ContentCandidate(Base):
    """Saralash va Kuratorlik bosqichidagi nomzodlar hovuzi."""
    __tablename__ = "content_candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    media_asset_id = Column(Integer, ForeignKey("media_assets.id"), nullable=False, index=True)
    status = Column(String(32), default="NEW", index=True) # NEW, ANALYZING, REVIEW, READY, SCHEDULED, PUBLISHED, REJECTED, FAILED
    content_score = Column(Float, default=0.0)
    audience_fit = Column(Float, default=0.0)
    diversity_penalty = Column(Float, default=0.0)
    fatigue_penalty = Column(Float, default=0.0)
    final_score = Column(Float, default=0.0, index=True)
    ai_explanation = Column(JSON, default=dict)
    is_breaking = Column(Boolean, default=False)
    confidence = Column(Float, default=0.8)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    media_asset = relationship("MediaAsset", back_populates="candidate")
    captions = relationship("Caption", back_populates="candidate", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="candidate")
    post = relationship("Post", back_populates="candidate", uselist=False)


class Caption(Base):
    """3 xil uslubdagi yaratilgan matnlar."""
    __tablename__ = "captions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("content_candidates.id"), nullable=False)
    style = Column(String(32), default="EMOTIONAL")  # INFORMATIVE, EMOTIONAL, INTERACTIVE
    title = Column(String(256), default="")
    body = Column(Text, default="")
    question = Column(String(256), default="")
    hashtags = Column(String(256), default="")
    full_caption = Column(Text, nullable=False)
    is_selected = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    candidate = relationship("ContentCandidate", back_populates="captions")


class MediaEdit(Base):
    """FFmpeg tahrirlash operatsiyalari."""
    __tablename__ = "media_edits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    media_asset_id = Column(Integer, ForeignKey("media_assets.id"), nullable=False)
    action = Column(String(32), default="KEEP_ORIGINAL") # KEEP_ORIGINAL, TRIM, CROP, RESIZE, STABILIZE, AUDIO_NORMALIZE, WATERMARK
    params = Column(JSON, default=dict)
    output_storage_key = Column(String(512), default="")
    output_path = Column(String(512), default="")
    status = Column(String(32), default="PENDING") # PENDING, PROCESSING, COMPLETED, FAILED
    created_at = Column(DateTime, default=datetime.utcnow)


class Schedule(Base):
    """Optimal e'lon qilish jadvali."""
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("content_candidates.id"), nullable=False)
    scheduled_time = Column(DateTime, nullable=False, index=True)
    status = Column(String(32), default="PENDING", index=True) # PENDING, PUBLISHED, CANCELLED
    priority = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

    candidate = relationship("ContentCandidate", back_populates="schedules")


class Post(Base):
    """Kanalga e'lon qilingan postlar jurnali."""
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("content_candidates.id"), nullable=False, index=True)
    target_channel = Column(String(128), nullable=False)
    target_message_id = Column(Integer, nullable=False, index=True)
    caption_used = Column(Text, default="")
    published_at = Column(DateTime, default=datetime.utcnow, index=True)
    status = Column(String(32), default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)

    candidate = relationship("ContentCandidate", back_populates="post")
    metrics = relationship("PostMetric", back_populates="post", cascade="all, delete-orphan")


class PostMetric(Base):
    """Vaqt bo'yicha ko'rishlar va engagement statistikasi."""
    __tablename__ = "post_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True)
    checked_at = Column(DateTime, default=datetime.utcnow)
    views = Column(Integer, default=0)
    reactions_count = Column(Integer, default=0)
    forwards = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    engagement_rate = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("Post", back_populates="metrics")


class AIPrediction(Base):
    """AI ning e'londan oldingi kutilma bahosi."""
    __tablename__ = "ai_predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("content_candidates.id"), nullable=False, index=True)
    expected_views_min = Column(Integer, default=0)
    expected_views_max = Column(Integer, default=0)
    expected_engagement_rate = Column(Float, default=0.0)
    predicted_at = Column(DateTime, default=datetime.utcnow)


class PredictionEvaluation(Base):
    """Prognoz va haqiqiy natija solishtirmasi."""
    __tablename__ = "prediction_evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    prediction_id = Column(Integer, ForeignKey("ai_predictions.id"), nullable=False)
    actual_views = Column(Integer, default=0)
    actual_engagement = Column(Float, default=0.0)
    accuracy_score = Column(Float, default=0.0) # 0.0 - 1.0
    evaluation_notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class StrategyRule(Base):
    """Strategik qoidalar va sozlamalar."""
    __tablename__ = "strategy_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), unique=True, index=True, nullable=False)
    value = Column(JSON, nullable=False)
    description = Column(String(256), default="")
    updated_at = Column(DateTime, default=datetime.utcnow)


class LearningEvent(Base):
    """O'rganish va model qoidalarini moslash jurnali."""
    __tablename__ = "learning_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(64), nullable=False)
    old_value = Column(String(256), default="")
    new_value = Column(String(256), default="")
    reason = Column(Text, default="")
    confidence = Column(Float, default=0.8)
    created_at = Column(DateTime, default=datetime.utcnow)


class AICost(Base):
    """AI xarajatlari va tokenlar monitoringi."""
    __tablename__ = "ai_costs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(64), nullable=False)
    request_type = Column(String(64), default="ANALYSIS")
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    latency_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class AdminAction(Base):
    """Admin harakatlari auditi."""
    __tablename__ = "admin_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action_type = Column(String(64), nullable=False)
    target_entity = Column(String(64), default="")
    target_id = Column(Integer, nullable=True)
    details = Column(JSON, default=dict)
    performed_by = Column(String(128), default="Admin")
    created_at = Column(DateTime, default=datetime.utcnow)


class SystemLog(Base):
    """Tizim telemetriyasi va xatolar jurnali."""
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    service = Column(String(64), default="System")
    event = Column(String(128), default="")
    severity = Column(String(16), default="INFO") # INFO, WARNING, ERROR, CRITICAL
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class LegacyProcessedMessage(Base):
    """Eski v1 kod bilan 100% orqaga moslik uchun jadval."""
    __tablename__ = "processed_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_channel = Column(String(128), nullable=False)
    source_message_id = Column(Integer, nullable=False)
    media_type = Column(String(32), default="")
    status = Column(String(32), nullable=False)
    quality_score = Column(Integer, default=0)
    reason = Column(Text, default="")
    target_message_id = Column(Integer, nullable=True)
    original_caption = Column(Text, nullable=True)
    enhanced_caption = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DuplicateGroup(Base):
    """Bir nechta manbalardan kelgan o'xshash medialar guruhi va eng yaxshi versiya."""
    __tablename__ = "duplicate_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_hash = Column(String(64), unique=True, index=True)
    representative_media_id = Column(Integer, ForeignKey("media_assets.id"), nullable=True)
    best_media_id = Column(Integer, ForeignKey("media_assets.id"), nullable=True)
    member_count = Column(Integer, default=1)
    status = Column(String(32), default="ACTIVE") # ACTIVE, MERGED, DISMISSED
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ContentDNA(Base):
    """Kanalning eng sara TOP 10% postlari profilining matematik modeli."""
    __tablename__ = "content_dna"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_name = Column(String(128), default="@muhtashamtraveluzz")
    ideal_duration_min = Column(Integer, default=8)
    ideal_duration_max = Column(Integer, default=30)
    top_categories = Column(JSON, default=lambda: ["Makkah", "Madinah", "Spiritual"])
    top_emotions = Column(JSON, default=lambda: ["Heartfelt", "Inspiring", "Peaceful"])
    top_keywords = Column(JSON, default=lambda: ["Umra", "Kaaba", "Duo", "Haram", "Madina"])
    target_mix = Column(JSON, default=lambda: {"Makkah": 30, "Madinah": 30, "Spiritual": 20, "Educational": 10, "Human Story": 10})
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ContentSequence(Base):
    """Postlar ketma-ketligi samaradorligi modeli."""
    __tablename__ = "content_sequences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sequence_pattern = Column(String(256), nullable=False) # e.g. "Makkah->Madinah->Spiritual"
    sample_count = Column(Integer, default=1)
    avg_engagement_boost = Column(Float, default=0.0)
    last_tested_at = Column(DateTime, default=datetime.utcnow)


class SimulationScenario(Base):
    """What-if simulyatsiya natijalari va ssenariylari."""
    __tablename__ = "simulation_scenarios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scenario_name = Column(String(128), nullable=False)
    candidate_ids = Column(JSON, default=list)
    predicted_views = Column(Integer, default=0)
    predicted_engagement = Column(Float, default=0.0)
    recommendation = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Report(Base):
    """Admin uchun yaratilgan hisobotlar arxivi va holati."""
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_type = Column(String(32), nullable=False) # MORNING, MIDDAY, EVENING, MANUAL
    report_date = Column(String(32), nullable=False) # YYYY-MM-DD
    idempotency_key = Column(String(128), unique=True, index=True)
    timezone = Column(String(64), default="Asia/Tashkent")
    summary_text = Column(Text, nullable=False)
    status = Column(String(32), default="GENERATED") # GENERATED, SENT, FAILED
    generation_time_ms = Column(Integer, default=0)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReportSnapshot(Base):
    """Hisobot yuborilgan vaqtdagi xom statistik ma'lumotlar snapshot'i."""
    __tablename__ = "report_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=False, index=True)
    data_snapshot = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class Alert(Base):
    """Tezkor tizim va kontent ogohlantirishlari."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    severity = Column(String(16), default="WARNING") # INFO, WARNING, CRITICAL
    alert_type = Column(String(64), nullable=False) # TELEGRAM_DOWN, DUPLICATE_SPIKE, AI_COST_SPIKE, PUBLISH_ERROR
    message = Column(Text, nullable=False)
    details = Column(JSON, default=dict)
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReportDeliveryLog(Base):
    """Hisobotlarni Telegram orqali adminga yetkazish jurnali."""
    __tablename__ = "report_delivery_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=False)
    recipient_id = Column(BigInteger, nullable=False)
    status = Column(String(32), default="SENT") # SENT, FAILED, RETRYING
    attempt_count = Column(Integer, default=1)
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)


class AnalyticsEvent(Base):
    """Barcha tizim hodisalari va konveyer qadamlarining to'liq auditi (Event Sourcing)."""
    __tablename__ = "analytics_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(64), nullable=False, index=True) # MEDIA_COLLECTED, DUPLICATE_BLOCKED, QUALITY_PASSED, etc.
    entity_id = Column(String(64), nullable=True)
    source = Column(String(128), nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
