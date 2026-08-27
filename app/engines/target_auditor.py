import asyncio
import os
import difflib
from pathlib import Path
from typing import Dict, Any, List, Set, Optional, Tuple
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import logger
from app.core.database import get_db_session
from app.models.schema import Post, MediaAsset, ContentCandidate, PostMetric


class TargetChannelAuditor:
    """
    Maqsadli kanalni (@muhtashamtraveluzz) doimiy chuqur skanerlovchi,
    tahlil qiluvchi va dublikatlardan 100% himoyalovchi doimiy Auditor.
    """

    def __init__(self):
        self.known_captions: List[str] = []
        self.known_file_sizes: Set[int] = set()
        self.known_durations: Set[float] = set()
        self.target_message_ids: Set[int] = set()
        self.is_synced: bool = False

    async def scan_and_analyze_target_channel(self, client: TelegramClient, limit: int = 100):
        """
        Maqsadli kanaldagi barcha mavjud postlarni skanerlaydi,
        xotiraga oladi va ularning statistikasi (views, reactions)ni yangilaydi.
        """
        target = settings.TARGET_CHANNEL
        logger.info(f"🔍 [TargetAuditor] Maqsadli kanal ({target}) chuqur skanerlanmoqda (Oxirgi {limit} ta post)...")

        try:
            target_entity = await client.get_entity(target)
            messages = await client.get_messages(target_entity, limit=limit)

            count = 0
            for msg in messages:
                if not msg:
                    continue

                self.target_message_ids.add(msg.id)

                # 1. Matnni xotiraga olish
                if msg.raw_text:
                    clean_text = msg.raw_text.strip().lower()
                    if clean_text not in self.known_captions:
                        self.known_captions.append(clean_text)

                # 2. Fayl hajmi va davomiyligini xotiraga olish
                if msg.media:
                    if isinstance(msg.media, MessageMediaDocument) and msg.media.document:
                        doc = msg.media.document
                        self.known_file_sizes.add(doc.size)
                        for attr in getattr(doc, "attributes", []):
                            if hasattr(attr, "duration"):
                                self.known_durations.add(round(float(attr.duration), 1))
                    elif isinstance(msg.media, MessageMediaPhoto) and msg.media.photo:
                        pass

                # 3. Statistikalarni (views, reactions) bazada yangilash
                async with get_db_session() as session:
                    existing_post = (await session.execute(
                        select(Post).where(Post.target_message_id == msg.id)
                    )).scalar_one_or_none()

                    if existing_post:
                        views = getattr(msg, "views", 0) or 0
                        forwards = getattr(msg, "forwards", 0) or 0
                        reactions_cnt = 0
                        if getattr(msg, "reactions", None) and hasattr(msg.reactions, "results"):
                            for r in msg.reactions.results:
                                reactions_cnt += getattr(r, "count", 0)

                        eng_rate = round(((reactions_cnt + forwards) / max(1, views)) * 100, 2) if views > 0 else 0.0

                        # PostMetric yozish
                        metric = PostMetric(
                            post_id=existing_post.id,
                            views=views,
                            reactions_count=reactions_cnt,
                            forwards=forwards,
                            engagement_rate=eng_rate
                        )
                        session.add(metric)
                        await session.commit()

                count += 1

            self.is_synced = True
            logger.info(f"✅ [TargetAuditor] Maqsadli kanal to'liq tahlil qilindi: {count} ta post xotirada faol.")

        except Exception as e:
            logger.warning(f"Maqsadli kanalni skanerlashda xatolik: {e}")

    def is_content_already_posted(
        self,
        caption: str = "",
        file_size: int = 0,
        duration: float = 0.0
    ) -> Tuple[bool, str]:
        """
        Kelgan yangi post maqsadli kanalda bor yoki yo'qligini 0.001 soniyada tekshiradi.
        """
        # 1. Matn o'xshashligi (60%+ o'xshashlik bo'lsa)
        if caption:
            cap_clean = caption.strip().lower()[:150]
            for past_cap in self.known_captions:
                sim = difflib.SequenceMatcher(None, cap_clean, past_cap[:150]).ratio()
                if sim >= 0.65:
                    return True, f"Matn o'xshashligi {sim*100:.1f}% (Kanalda mavjud)"

        # 2. Fayl hajmi tekshiruvi (aniq yoki yaqin o'lcham)
        if file_size > 0:
            if file_size in self.known_file_sizes:
                return True, "Fayl hajmi 100% bir xil (Kanalda mavjud)"
            for k_size in self.known_file_sizes:
                if abs(k_size - file_size) < 2048: # 2 KB farq
                    return True, "Fayl baytlari va hajmi bir xil (Kanalda mavjud)"

        # 3. Video davomiyligi
        if duration > 0:
            dur_round = round(duration, 1)
            if dur_round in self.known_durations:
                # Agar davomiylik bir xil bo'lsa va matnda ham o'xshashlik bo'lsa
                if caption:
                    cap_clean = caption.strip().lower()[:100]
                    for past_cap in self.known_captions:
                        if difflib.SequenceMatcher(None, cap_clean, past_cap[:100]).ratio() > 0.45:
                            return True, "Davomiylik va mavzu bir xil (Kanalda mavjud)"

        return False, "Yangi kontent"


target_auditor = TargetChannelAuditor()
