import os
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageMediaPhoto,
    MessageMediaDocument,
    DocumentAttributeVideo,
    DocumentAttributeAnimated,
    ChannelParticipantAdmin,
    ChannelParticipantCreator
)
from telethon.tl.functions.channels import GetParticipantRequest
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import logger
from app.core.database import get_db_session
from app.core.queue import queue_manager, TaskMessage
from app.models.schema import Source, SourceMessage, MediaAsset, ContentCandidate, MediaAnalysis, Post
from app.storage import get_storage_provider
from app.engines.quality import quality_engine
from app.engines.duplicate import duplicate_engine
from app.engines.ai_provider import get_ai_provider
from app.engines.scoring import scoring_engine
from app.engines.curator import curator_engine
from app.engines.captioner import caption_engine
from app.engines.scheduler import scheduler_engine
from app.engines.publisher import telegram_publisher
from app.engines.predictor import predictor_engine
from app.engines.media_creator import media_creator
from app.integrations.google_sheets import google_sheets


def is_round_video_media(media) -> bool:
    """Telegram dumaloq video xabari (Video Note / Round Video) ekanligini aniqlaydi."""
    if isinstance(media, MessageMediaDocument) and media.document:
        doc = media.document
        if any(isinstance(attr, DocumentAttributeVideo) and getattr(attr, "round_message", False) for attr in (doc.attributes or [])):
            return True
    return False


def is_video_media(media) -> bool:
    if isinstance(media, MessageMediaDocument) and media.document:
        doc = media.document
        if doc.mime_type and doc.mime_type.startswith("video/"):
            return True
        if any(isinstance(attr, (DocumentAttributeVideo, DocumentAttributeAnimated)) for attr in (doc.attributes or [])):
            return True
    return False


def is_photo_media(media) -> bool:
    if isinstance(media, MessageMediaPhoto):
        return True
    if isinstance(media, MessageMediaDocument) and media.document:
        doc = media.document
        if doc.mime_type and doc.mime_type.startswith("image/"):
            return True
    return False


class TelegramMediaCollector:
    """Manba kanallarni kuzatuvchi va mediya yig'uvchi bosh collector."""

    def __init__(self):
        if settings.TELEGRAM_SESSION_STRING:
            session = StringSession(settings.TELEGRAM_SESSION_STRING)
        else:
            session = settings.TELEGRAM_SESSION_NAME

        self.client = TelegramClient(session, settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH)
        self.storage = get_storage_provider()
        self.source_map: Dict[int, str] = {}

    async def initialize(self):
        await self.client.connect()
        if not await self.client.is_user_authorized():
            await self.client.start()

        me = await self.client.get_me()
        logger.info(f"🔑 Telegram client faollashtirildi: {getattr(me, 'first_name', '')} (@{getattr(me, 'username', '')})")

        # Worker handlerlarni ro'yxatga olish
        self._register_pipeline_handlers()

    def _register_pipeline_handlers(self):
        """Ko'p bosqichli avtonom qayta ishlash konveyerini ulaydi."""
        queue_manager.register_handler("PROCESS_MEDIA", self._handle_process_media)

    async def _handle_process_media(self, task: TaskMessage):
        payload = task.payload
        file_path = Path(payload["file_path"])
        media_type = payload["media_type"]
        source_name = payload["source_name"]
        source_msg_id = payload["source_message_id"]
        original_caption = payload.get("original_caption", "")

        logger.info(f"⚡️ [Pipeline] Nomzod media to'liq tahlil qilinmoqda: {source_name}:{source_msg_id}")

        from app.core.events import event_bus
        await event_bus.emit("MEDIA_DOWNLOADED", entity_id=source_msg_id, source=source_name, metadata={"media_type": media_type})

        # 1. Texnik sifatni tekshirish
        if media_type == "photo":
            tech_quality = quality_engine.evaluate_photo(file_path)
        else:
            tech_quality = quality_engine.evaluate_video(file_path)

        await event_bus.emit("QUALITY_EVALUATED", entity_id=source_msg_id, source=source_name, metadata={"score": tech_quality.score, "is_hd": tech_quality.is_hd, "issues": tech_quality.issues})

        # 1.5. Maqsadli kanalda (@muhtashamtraveluzz) bor-yo'qligini tekshirish
        from app.engines.target_auditor import target_auditor
        already_in_target, target_reason = target_auditor.is_content_already_posted(
            caption=original_caption,
            file_size=file_path.stat().st_size if file_path.exists() else 0,
            duration=tech_quality.duration
        )
        if already_in_target:
            logger.info(f"⛔️ [Pipeline] Kontent maqsadli kanalda (@muhtashamtraveluzz) allaqachon mavjud! ({target_reason}). Bekor qilindi.")
            await event_bus.emit("DUPLICATE_BLOCKED", entity_id=source_msg_id, source=source_name, metadata={"reason": target_reason})
            return

        # 2. Dublikatni tekshirish (Bazadagi barcha oldingi media bilan)
        is_dup, dup_id, match_type, sim_score = await duplicate_engine.check_duplicate(file_path, media_type)
        if is_dup:
            logger.info(f"⏭ [Pipeline] Dublikat aniqlandi ({match_type}, sim: {sim_score}). Tashlab ketilmoqda.")
            await event_bus.emit("DUPLICATE_BLOCKED", entity_id=source_msg_id, source=source_name, metadata={"sim_score": sim_score, "match_type": match_type})
            return

        # 3. Storage ga saqlash
        sha256 = duplicate_engine.calculate_sha256(file_path)
        phash_str, dhash_str = duplicate_engine.calculate_visual_hashes(file_path, media_type)
        dest_key = f"{media_type}s/{sha256[:16]}_{file_path.name}"
        stored_key = await self.storage.save(file_path, dest_key)

        # 4. Bazaga SourceMessage va MediaAsset yozish
        async with get_db_session() as session:
            # Manbani olish yoki yaratish
            s_obj = (await session.execute(select(Source).where(Source.username == source_name))).scalar_one_or_none()
            if not s_obj:
                s_obj = Source(username=source_name, title=source_name, status="ACTIVE")
                session.add(s_obj)
                await session.flush()

            msg_obj = SourceMessage(
                source_id=s_obj.id,
                source_message_id=source_msg_id,
                media_type=media_type,
                raw_text=original_caption
            )
            session.add(msg_obj)
            await session.flush()

            asset_obj = MediaAsset(
                source_message_id=msg_obj.id,
                storage_provider=settings.STORAGE_PROVIDER,
                storage_key=stored_key,
                local_path=str(file_path),
                mime_type=f"{media_type}/jpeg" if media_type == "photo" else f"{media_type}/mp4",
                file_size=file_path.stat().st_size if file_path.exists() else 0,
                width=tech_quality.width,
                height=tech_quality.height,
                duration=tech_quality.duration,
                sha256_hash=sha256,
                phash=phash_str,
                dhash=dhash_str
            )
            session.add(asset_obj)
            await session.flush()
            asset_id = asset_obj.id
            await session.commit()

        # 5. AI Vision ko'p o'lchovli tahlili
        ai = get_ai_provider()
        analysis = await ai.analyze_media(file_path, media_type, original_caption)

        # 6. Scoring hisoblash
        score_res = scoring_engine.calculate_score(analysis, tech_quality, source_trust_score=1.0)
        content_score = score_res["score"]

        # 7. Nomzodni yaratish
        async with get_db_session() as session:
            session.add(MediaAnalysis(
                media_asset_id=asset_id,
                category=analysis.category,
                sub_category=analysis.sub_category,
                tags=analysis.tags,
                visual_quality=analysis.visual_quality,
                emotional_impact=analysis.emotional_impact,
                relevance=analysis.relevance,
                uniqueness=analysis.uniqueness,
                freshness=analysis.freshness,
                information_value=analysis.information_value,
                risk_level=analysis.risk_level,
                confidence=analysis.confidence,
                recommendation=analysis.recommendation,
                reason=analysis.reason
            ))
            candidate = ContentCandidate(
                media_asset_id=asset_id,
                status="NEW",
                content_score=content_score,
                confidence=analysis.confidence
            )
            session.add(candidate)
            await session.commit()
            candidate_id = candidate.id

        # 8. Kuratsiya va qaror izohi
        curation = await curator_engine.curate_candidate(candidate_id)
        final_score = curation["final_score"]

        if final_score < 60.0 or analysis.risk_level == "HIGH":
            logger.info(f"⛔️ [Pipeline] Nomzod {candidate_id} rad etildi (Ball: {final_score}, Xavf: {analysis.risk_level})")
            asyncio.create_task(google_sheets.append_row({
                "source_channel": source_name,
                "source_message_id": source_msg_id,
                "media_type": media_type,
                "category": analysis.category,
                "final_score": final_score,
                "status": "REJECTED",
                "reason": analysis.reason
            }))
            return

        # 9. Matnlar yaratish (Dumaloq video bo'lsa matn yozilmaydi)
        if media_type == "video_note":
            selected_style = "ROUND_CLEAN"
            selected_caption = ""
            logger.info(f"⭕️ [Pipeline] Dumaloq video (Video Note) aniqlandi. Matnsiz, toza shaklda e'lon qilinadi.")
        else:
            selected_style, selected_caption = await caption_engine.create_and_store_captions(
                candidate_id=candidate_id,
                category=analysis.category,
                original_caption=original_caption,
                analysis_summary=analysis.reason
            )

        # 10. AI Prediction
        await predictor_engine.predict_for_candidate(candidate_id)

        # 11. Publishing yoki Scheduling qarori
        if settings.GOVERNANCE_MODE == "AUTO" or (settings.GOVERNANCE_MODE == "SEMI_AUTO" and analysis.confidence >= settings.MIN_AUTO_CONFIDENCE):
            logger.info(f"✅ [Pipeline] Nomzod {candidate_id} tasdiqlandi! Kanalga nashr qilinmoqda...")
            await telegram_publisher.publish_candidate(self.client, candidate_id)
            asyncio.create_task(google_sheets.append_row({
                "source_channel": source_name,
                "source_message_id": source_msg_id,
                "media_type": media_type,
                "category": analysis.category,
                "final_score": final_score,
                "status": "POSTED",
                "reason": curation.get("summary", ""),
                "enhanced_caption": selected_caption
            }))
        else:
            logger.info(f"⏳ [Pipeline] Nomzod {candidate_id} moderatsiya (Review) kutmoqda.")
            asyncio.create_task(google_sheets.append_row({
                "source_channel": source_name,
                "source_message_id": source_msg_id,
                "media_type": media_type,
                "category": analysis.category,
                "final_score": final_score,
                "status": "REVIEW",
                "reason": curation.get("summary", ""),
                "enhanced_caption": selected_caption
            }))

    async def ingest_message(self, message, source_channel: str):
        if not message.media:
            return

        if is_round_video_media(message.media):
            media_type = "video_note"
        elif is_photo_media(message.media):
            media_type = "photo"
        elif is_video_media(message.media):
            media_type = "video"
        else:
            media_type = None

        if not media_type:
            return

        # Tekshirish: avval qayta ishlanganmi
        async with get_db_session() as session:
            existing_asset = (await session.execute(
                select(MediaAsset)
                .join(SourceMessage, MediaAsset.source_message_id == SourceMessage.id)
                .join(Source, SourceMessage.source_id == Source.id)
                .where(Source.username == source_channel, SourceMessage.source_message_id == message.id)
            )).scalar_one_or_none()

            if existing_asset:
                return

        logger.info(f"📥 Yangi {media_type} topildi ({source_channel}:{message.id}). Yuklab olinmoqda...")
        try:
            temp_file = await asyncio.wait_for(message.download_media(file=settings.DOWNLOAD_DIR), timeout=45.0)
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Faylni yuklab olish vaqti tugadi (Timeout 45s): {source_channel}:{message.id}")
            return
        except Exception as dl_err:
            logger.warning(f"⚠️ Faylni yuklab olishda xatolik: {dl_err}")
            return

        if not temp_file or not os.path.exists(temp_file):
            return

        await queue_manager.enqueue("PROCESS_MEDIA", {
            "file_path": str(temp_file),
            "media_type": media_type,
            "source_name": source_channel,
            "source_message_id": message.id,
            "original_caption": message.raw_text or ""
        })

    async def sync_target_channel_history(self, limit: int = 50):
        """Maqsadli kanaldagi (@muhtashamtraveluzz) mavjud postlarni skanerlab, dublikatlar bazasiga kiritadi."""
        logger.info(f"🔍 Maqsadli kanal (@muhtashamtraveluzz) tarixi sinxronlanmoqda (Oxirgi {limit} ta post)...")
        try:
            target_entity = await self.client.get_entity(settings.TARGET_CHANNEL)
            messages = await self.client.get_messages(target_entity, limit=limit)
            synced_count = 0
            
            async with get_db_session() as session:
                s_target = (await session.execute(select(Source).where(Source.username == settings.TARGET_CHANNEL))).scalar_one_or_none()
                if not s_target:
                    s_target = Source(username=settings.TARGET_CHANNEL, title="Target Channel", status="ACTIVE")
                    session.add(s_target)
                    await session.flush()

                for msg in messages:
                    if not msg:
                        continue
                    
                    exists = (await session.execute(
                        select(Post).where(Post.target_message_id == msg.id)
                    )).scalar_one_or_none()
                    if exists:
                        continue

                    media_type = "photo" if is_photo_media(msg.media) else ("video" if is_video_media(msg.media) else "text")

                    src_msg = SourceMessage(
                        source_id=s_target.id,
                        source_message_id=msg.id,
                        media_type=media_type,
                        raw_text=msg.raw_text or ""
                    )
                    session.add(src_msg)
                    await session.flush()

                    asset_obj = MediaAsset(
                        source_message_id=src_msg.id,
                        storage_provider="local",
                        storage_key=f"target_synced/{msg.id}",
                        local_path="",
                        mime_type=f"{media_type}/jpeg" if media_type == "photo" else f"{media_type}/mp4",
                        file_size=getattr(getattr(msg, "media", None), "document", None).size if hasattr(getattr(msg, "media", None), "document") and getattr(msg.media, "document") else 0
                    )
                    session.add(asset_obj)
                    await session.flush()

                    candidate = ContentCandidate(
                        media_asset_id=asset_obj.id,
                        status="PUBLISHED",
                        content_score=90.0,
                        final_score=90.0,
                        confidence=1.0
                    )
                    session.add(candidate)
                    await session.flush()

                    post = Post(
                        candidate_id=candidate.id,
                        target_channel=settings.TARGET_CHANNEL,
                        target_message_id=msg.id,
                        caption_used=msg.raw_text or "",
                        status="ACTIVE"
                    )
                    session.add(post)
                    synced_count += 1

                await session.commit()
            logger.info(f"✅ Maqsadli kanaldan {synced_count} ta mavjud postlar bazaga sinxronlashtirildi.")
        except Exception as e:
            logger.warning(f"Maqsadli kanal tarixini sinxronlashtirishda xatolik: {e}")

    async def scan_and_process_recent_source_messages(self, limit: int = 15):
        """Manba kanallardagi oxirgi postlarni skanerlab, tahlil va nashr konveyeriga jo'natadi."""
        logger.info(f"🔍 Manba kanallaridagi oxirgi {limit} ta post tekshirilmoqda va saralanmoqda...")
        for source in settings.SOURCE_CHANNELS:
            try:
                entity = await self.client.get_entity(source)
                messages = await self.client.get_messages(entity, limit=limit)
                for msg in reversed(messages):
                    if msg.media:
                        await self.ingest_message(msg, source)
            except Exception as e:
                logger.warning(f"Manba kanalni skaner qilishda xatolik ({source}): {e}")

    async def start_listening(self):
        source_entities = []
        for source in settings.SOURCE_CHANNELS:
            try:
                entity = await self.client.get_entity(source)
                source_entities.append(entity)
                self.source_map[entity.id] = source
                logger.info(f"✅ Manba kanal tinglanmoqda: {source}")
            except Exception as e:
                logger.error(f"Manba kanalga ulanishda xatolik ({source}): {e}")

        if not source_entities:
            logger.error("Hech qaysi manba kanal topilmadi!")
            return

        # Real-vaqt hodisalari
        @self.client.on(events.NewMessage(chats=source_entities))
        async def on_new_post(event):
            chat = await event.get_chat()
            source_name = self.source_map.get(getattr(chat, "id", 0), f"@{getattr(chat, 'username', 'unknown')}")
            await self.ingest_message(event.message, source_name)

        logger.info("🟢 Telegram Collector to'liq tayyor va real-vaqtda postlarni qabul qilmoqda.")


collector = TelegramMediaCollector()
