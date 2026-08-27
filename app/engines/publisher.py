import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional
from telethon import TelegramClient
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import logger
from app.core.database import get_db_session
from app.models.schema import ContentCandidate, Post, Caption, MediaAsset, LegacyProcessedMessage

_publish_lock = asyncio.Lock()


class TelegramPublisher:
    """Idempotent Telegram nashriyotchi (Publisher)."""

    @classmethod
    async def publish_candidate(
        cls,
        client: TelegramClient,
        candidate_id: int,
        target_channel: Optional[str] = None
    ) -> Optional[int]:
        target = target_channel or settings.TARGET_CHANNEL

        async with _publish_lock:
            async with get_db_session() as session:
                candidate = await session.get(ContentCandidate, candidate_id)
                if not candidate:
                    logger.error(f"Nomzod topilmadi: {candidate_id}")
                    return None

                # Idempotency tekshiruvi: Agar bu nomzod avval nashr qilingan bo'lsa
                existing_post = (await session.execute(
                    select(Post).where(Post.candidate_id == candidate_id)
                )).scalar_one_or_none()

                if existing_post:
                    logger.warning(f"Nomzod {candidate_id} avval nashr qilingan (Target Msg ID: {existing_post.target_message_id}). Qayta yuborilmaydi.")
                    return existing_post.target_message_id

                asset = await session.get(MediaAsset, candidate.media_asset_id)
                selected_caption = (await session.execute(
                    select(Caption.full_caption).where(Caption.candidate_id == candidate_id, Caption.is_selected == True)
                )).scalar_one_or_none() or ""

                file_path = Path(asset.local_path)
                if not file_path.exists():
                    logger.error(f"Nashr qilish uchun fayl topilmadi: {file_path}")
                    return None

                # 0. Telegramdagi Maqsadli Kanalning oxirgi 15 ta postini to'g'ridan-to'g'ri tekshirish
                try:
                    import difflib
                    target_entity = await client.get_entity(target)
                    recent_posts = await client.get_messages(target_entity, limit=15)
                    for r_msg in recent_posts:
                        # 1. Matn o'xshashligi tekshiruvi
                        if r_msg.raw_text and selected_caption:
                            sim = difflib.SequenceMatcher(None, r_msg.raw_text[:120].lower(), selected_caption[:120].lower()).ratio()
                            if sim > 0.70:
                                logger.warning(f"⛔️ [Publisher] Maqsadli kanalda (@muhtashamtraveluzz) juda o'xshash post allaqachon mavjud! (O'xshashlik: {sim*100:.1f}%). Bekor qilindi.")
                                candidate.status = "DUPLICATE_SUPPRESSED"
                                await session.commit()
                                return r_msg.id

                        # 2. Fayl hajmi va davomiyligi bo'yicha tekshirish
                        if r_msg.media and hasattr(r_msg.media, "document") and r_msg.media.document:
                            r_size = r_msg.media.document.size
                            if asset.file_size and abs(r_size - asset.file_size) < 1024:
                                logger.warning(f"⛔️ [Publisher] Maqsadli kanalda (@muhtashamtraveluzz) aynan shu media fayl allaqachon mavjud! Bekor qilindi.")
                                candidate.status = "DUPLICATE_SUPPRESSED"
                                await session.commit()
                                return r_msg.id
                except Exception as e:
                    logger.debug(f"Maqsadli kanalni tekshirishda xatolik: {e}")

                logger.info(f"🚀 Kanalga joylanmoqda ({target}): Candidate ID {candidate_id}...")

                is_round = "note" in str(asset.mime_type or "").lower() or (not selected_caption)
                final_caption = None if is_round or not selected_caption else selected_caption

                sent_msg = None
                try:
                    if is_round:
                        logger.info("⭕️ [Publisher] Dumaloq video (Video Note) matnsiz toza shaklda Telegramga chiqarilmoqda...")
                        sent_msg = await client.send_file(
                            target,
                            file=str(file_path),
                            video_note=True
                        )
                    else:
                        sent_msg = await client.send_file(
                            target,
                            file=str(file_path),
                            caption=final_caption,
                            parse_mode="markdown"
                        )
                except Exception as e:
                    logger.warning(f"Nashr qilishda xatolik ({e}), muqobil format bilan qayta urinilmoqda...")
                    try:
                        sent_msg = await client.send_file(
                            target,
                            file=str(file_path),
                            caption=final_caption,
                            parse_mode=None
                        )
                    except Exception as e2:
                        logger.error(f"❌ Telegram kanaliga post jo'natish butunlay muvaffaqiyatsiz bo'ldi ({target}): {e2}")
                        candidate.status = "FAILED"
                        await session.commit()
                        return None

                if sent_msg:
                    new_post = Post(
                        candidate_id=candidate_id,
                        target_channel=target,
                        target_message_id=sent_msg.id,
                        caption_used=selected_caption,
                        published_at=datetime.utcnow(),
                        status="ACTIVE"
                    )
                    session.add(new_post)
                    candidate.status = "PUBLISHED"

                    # Orqaga moslik uchun Legacy jadvalga ham yozish
                    score_val = int((candidate.final_score or 70.0) / 10)
                    session.add(LegacyProcessedMessage(
                        source_channel=target,
                        source_message_id=sent_msg.id,
                        media_type=asset.mime_type or "media",
                        status="POSTED",
                        quality_score=score_val,
                        reason="Autonomous AI Media Creator tomonidan joylandi",
                        target_message_id=sent_msg.id,
                        enhanced_caption=selected_caption,
                        created_at=datetime.utcnow()
                    ))

                    await session.commit()
                    
                    from app.core.events import event_bus
                    await event_bus.emit("POST_PUBLISHED", entity_id=new_post.id, source=target, metadata={"target_msg_id": sent_msg.id, "candidate_id": candidate_id})

                    logger.info(f"🎉 Post muvaffaqiyatli kanalga chiqdi! (Target Msg ID: {sent_msg.id})")
                    return sent_msg.id

            return None


telegram_publisher = TelegramPublisher()
