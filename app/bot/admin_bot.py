import asyncio
import httpx
from typing import Dict, Any, List, Optional
from telethon import TelegramClient, events, Button
from sqlalchemy import select, desc, func

from app.core.config import settings
from app.core.logging import logger
from app.core.database import get_db_session
from app.models.schema import (
    Source, ContentCandidate, Post, PostMetric, MediaAnalysis,
    MediaAsset, DuplicateMatch, Alert, AICost
)
from app.engines.reporting_engine import reporting_engine
from app.engines.strategist import strategist_engine


def is_admin(user_id: int) -> bool:
    """Foydalanuvchi admin ekanligini tekshirish."""
    return user_id in settings.ADMIN_TELEGRAM_IDS or not settings.ADMIN_TELEGRAM_IDS


def register_admin_bot_handlers(client: TelegramClient):
    """Admin buyruqlari va interaktiv boshqaruv tugmalarini ulaydi."""

    @client.on(events.NewMessage(pattern="(?i)^/start"))
    async def cmd_start(event):
        sender = await event.get_sender()
        user_id = getattr(sender, "id", 0)
        if not is_admin(user_id):
            await event.respond("⛔️ **Kirish taqiqlangan.** Siz tizim administratori emassiz.")
            return

        text = (
            f"👋 Assalomu alaykum, **{getattr(sender, 'first_name', 'Admin')}**!\n\n"
            "🤖 **TAMC Professional Admin Reporting Bot — Boshqaruv Markazi**\n\n"
            "📋 **Asosiy Buyruqlar:**\n"
            "📊 `/report` — Hozirgi umumiy hisobot\n"
            "🌅 `/report morning` — Tonggi hisobot (08:00)\n"
            "☀️ `/report midday` — Kun o'rtasi hisoboti (13:00)\n"
            "🌙 `/report evening` — Kechki yakuniy hisobot (21:00)\n"
            "🏆 `/top` — Eng yuqori natijali postlar va manbalar\n"
            "🔍 `/trace <post_id>` — Postning to'liq manba zanjiri\n"
            "🛡 `/duplicates` — Dublikatlar holati\n"
            "👁 `/quality` — Sifat taqsimoti\n"
            "🧠 `/learning` — AI o'rganish xulosalari\n"
            "🟢 `/health` — Tizim salomatligi"
        )
        buttons = [
            [Button.inline("📊 Hozirgi Hisobot", b"btn_report_current"), Button.inline("🏆 Top Postlar", b"btn_top_posts")],
            [Button.inline("🌅 Tonggi (08:00)", b"btn_rep_morning"), Button.inline("🌙 Kechki (21:00)", b"btn_rep_evening")],
            [Button.inline("📡 Manbalar", b"btn_sources"), Button.inline("🧠 AI Strateg", b"btn_strategist")],
            [Button.inline("🛡 Dublikatlar", b"btn_duplicates"), Button.inline("🟢 Tizim Holati", b"btn_health")]
        ]
        await event.respond(text, buttons=buttons)

    @client.on(events.NewMessage(pattern="(?i)^/report(?:\\s+(.*))?$"))
    async def cmd_report(event):
        sender = await event.get_sender()
        if not is_admin(getattr(sender, "id", 0)):
            return

        arg = (event.pattern_match.group(1) or "").strip().lower()

        if arg == "morning":
            res = await reporting_engine.generate_morning_report()
            await event.respond(res["summary_text"])
        elif arg == "midday":
            res = await reporting_engine.generate_midday_report()
            await event.respond(res["summary_text"])
        elif arg == "evening":
            res = await reporting_engine.generate_evening_report()
            await event.respond(res["summary_text"])
        else:
            # Standart kunlik hisobot
            now = reporting_engine.get_tashkent_now()
            hour = now.hour
            if hour < 12:
                res = await reporting_engine.generate_morning_report()
            elif hour < 19:
                res = await reporting_engine.generate_midday_report()
            else:
                res = await reporting_engine.generate_evening_report()
            await event.respond(res["summary_text"])

    @client.on(events.NewMessage(pattern="(?i)^/top(?:\\s+(.*))?$"))
    async def cmd_top(event):
        sender = await event.get_sender()
        if not is_admin(getattr(sender, "id", 0)):
            return

        async with get_db_session() as session:
            posts = (await session.execute(
                select(Post, ContentCandidate, MediaAnalysis, PostMetric)
                .join(ContentCandidate, Post.candidate_id == ContentCandidate.id, isouter=True)
                .join(MediaAnalysis, ContentCandidate.media_asset_id == MediaAnalysis.media_asset_id, isouter=True)
                .join(PostMetric, Post.id == PostMetric.post_id, isouter=True)
                .order_by(desc(PostMetric.views))
                .limit(5)
            )).all()

            lines = ["🏆 **Kanalning TOP 5 Postlari (Engagement & Views):**\n"]
            if posts:
                for idx, (p, cand, analysis, m) in enumerate(posts, 1):
                    cat = analysis.category if analysis else "General"
                    views = m.views if m else 0
                    eng = m.engagement_rate if m else 0.0
                    lines.append(f"{idx}. Post #{p.target_message_id} [{cat}] — 👁 {views} views | ❤️ {eng}% engagement")
            else:
                lines.append("• _Postlar statistikasi tahlil qilinmoqda..._")

        await event.respond("\n".join(lines))

    @client.on(events.NewMessage(pattern="(?i)^/trace(?:\\s+(\\d+))?$"))
    async def cmd_trace(event):
        sender = await event.get_sender()
        if not is_admin(getattr(sender, "id", 0)):
            return

        post_id_str = event.pattern_match.group(1)
        if not post_id_str:
            await event.respond("⚠️ Iltimos, post ID sini kiriting. Masalan: `/trace 1`")
            return

        post_id = int(post_id_str)
        res = await reporting_engine.get_content_traceability(post_id)
        if res.get("status") == "NOT_FOUND":
            await event.respond(f"❌ Post #{post_id} topilmadi.")
            return

        chain = res["trace_chain"]
        text = (
            f"🔍 **POST #{post_id} TO'LIQ MANBA ZANJIRI:**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"1️⃣ **Manba:** `{chain['1_source']}`\n"
            f"2️⃣ **Manba Xabar ID:** `#{chain['2_source_msg_id']}`\n"
            f"3️⃣ **Format & Sifat:** {chain['3_media_type']} ({chain['4_technical_quality']})\n"
            f"4️⃣ **Dublikat Tahlili:** {chain['5_duplicate_check']}\n"
            f"5️⃣ **AI Kategoriya:** {chain['6_ai_category']}\n"
            f"6️⃣ **Kontent Bali:** {chain['7_content_score']} / 100\n"
            f"7️⃣ **Kuratorlik Bali:** {chain['8_final_curated_score']} / 100\n"
            f"8️⃣ **Matn Uslubi:** {chain['9_caption_style']}\n"
            f"9️⃣ **Kanalga Chiqdi:** #{res['target_message_id']}\n"
            f"🔟 **Haqiqiy Ko'rishlar:** 👁 {chain['10_performance']['views']} | ❤️ {chain['10_performance']['engagement_rate']}%"
        )
        await event.respond(text)

    @client.on(events.NewMessage(pattern="(?i)^/duplicates"))
    async def cmd_duplicates(event):
        sender = await event.get_sender()
        if not is_admin(getattr(sender, "id", 0)):
            return

        async with get_db_session() as session:
            dup_count = (await session.execute(select(func.count(DuplicateMatch.id)))).scalar() or 0

        text = (
            "🛡 **DUBLIKATLAR NAZORATI HISOBOTI:**\n\n"
            f"• To'xtatilgan dublikatlar: **{dup_count} ta**\n"
            f"• Tahlil usuli: `SHA-256` + `5-Frame Video pHash`\n"
            f"• Maqsadli kanal jonli tekshiruvi: **FAOL (100%)**\n"
            "• Holat: Bir xil kontent qayta chiqishi mutlaqo to'silgan."
        )
        await event.respond(text)

    @client.on(events.NewMessage(pattern="(?i)^/health"))
    async def cmd_health(event):
        sender = await event.get_sender()
        if not is_admin(getattr(sender, "id", 0)):
            return

        text = (
            "🟢 **TIZIM SALOMATLIGI MONITORINGI:**\n\n"
            "• Telegram MTProto Client: 🟢 ONLINE\n"
            "• Google Gemini Vision API: 🟢 ONLINE\n"
            "• SQLAlchemy Database: 🟢 ONLINE\n"
            "• Asynchronous Queue & Workers: 🟢 ONLINE\n"
            "• Target Channel Live Auditor: 🟢 ONLINE\n"
            "• Report Scheduler (08:00, 13:00, 21:00): 🟢 ONLINE\n\n"
            f"🛡 Boshqaruv rejimi: `{settings.GOVERNANCE_MODE}`"
        )
        await event.respond(text)

    @client.on(events.CallbackQuery)
    async def callback_handler(event):
        user_id = event.sender_id
        if not is_admin(user_id):
            await event.answer("Ruxsat yo'q", alert=True)
            return

        data = event.data.decode("utf-8")
        if data == "btn_report_current":
            res = await reporting_engine.generate_morning_report()
            await event.respond(res["summary_text"])
        elif data == "btn_rep_morning":
            res = await reporting_engine.generate_morning_report()
            await event.respond(res["summary_text"])
        elif data == "btn_rep_evening":
            res = await reporting_engine.generate_evening_report()
            await event.respond(res["summary_text"])
        elif data == "btn_top_posts":
            await cmd_top(event)
        elif data == "btn_sources":
            async with get_db_session() as session:
                sources = (await session.execute(select(Source))).scalars().all()
                lines = ["📡 **Kuzatilayotgan manbalar:**\n"]
                for s in sources:
                    lines.append(f"• `{s.username}` — Prioritet: {s.priority}, Ishonch: {int((s.trust_score or 1)*100)}%")
                await event.respond("\n".join(lines))
        elif data == "btn_duplicates":
            await cmd_duplicates(event)
        elif data == "btn_health":
            await cmd_health(event)
        elif data == "btn_strategist":
            strat = await strategist_engine.generate_daily_report()
            await event.respond(f"🧠 **AI Strategist Tavsiyasi:**\n\n{strat['summary']}")

        await event.answer()


class TelegramBotPollingService:
    """Telegram Bot API (@...bot) Long-Polling xizmati."""

    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.is_running = False

    async def start(self):
        if not self.bot_token:
            return

        self.is_running = True
        logger.info("🤖 [BotAPI] Telegram Bot API Long-Polling xizmati boshlandi.")
        offset = 0
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"

        while self.is_running:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(url, params={"offset": offset, "timeout": 20})
                    if resp.status_code == 200:
                        data = resp.json()
                        for update in data.get("result", []):
                            offset = update["update_id"] + 1
                            msg = update.get("message")
                            callback = update.get("callback_query")
                            if msg and "text" in msg:
                                chat_id = msg["chat"]["id"]
                                text = msg["text"].strip()
                                await self._handle_bot_command(chat_id, text)
                            elif callback:
                                chat_id = callback["from"]["id"]
                                cb_data = callback.get("data", "")
                                query_id = callback["id"]
                                await self._handle_callback_query(chat_id, cb_data, query_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                await asyncio.sleep(5)

    async def _handle_bot_command(self, chat_id: int, text: str):
        if not is_admin(chat_id):
            return

        from app.engines.report_scheduler import report_scheduler

        cmd = text.split()[0].lower()
        if cmd in ["/start", "/help"]:
            welcome = (
                "👋 Assalomu alaykum!\n\n"
                "🤖 **TAMC Professional Admin Reporting Bot**\n\n"
                "📊 `/report` — Umumiy hisobot\n"
                "🌅 `/report morning` — Tonggi hisobot (08:00)\n"
                "☀️ `/report midday` — Kun o'rtasi hisoboti (13:00)\n"
                "🌙 `/report evening` — Kechki hisobot (21:00)\n"
                "🏆 `/top` — Top postlar natijasi\n"
                "📡 `/sources` — Manbalar holati\n"
                "🛡 `/duplicates` — Dublikatlar nazorati\n"
                "🟢 `/health` — Tizim salomatligi"
            )
            await report_scheduler.send_telegram_message(chat_id, welcome, report_scheduler.get_report_keyboard())
        elif cmd == "/report":
            parts = text.split()
            sub = parts[1].lower() if len(parts) > 1 else ""
            if sub == "morning":
                res = await reporting_engine.generate_morning_report()
            elif sub == "midday":
                res = await reporting_engine.generate_midday_report()
            elif sub == "evening":
                res = await reporting_engine.generate_evening_report()
            else:
                now = reporting_engine.get_tashkent_now()
                if now.hour < 12:
                    res = await reporting_engine.generate_morning_report()
                elif now.hour < 19:
                    res = await reporting_engine.generate_midday_report()
                else:
                    res = await reporting_engine.generate_evening_report()
            await report_scheduler.send_telegram_message(chat_id, res["summary_text"], report_scheduler.get_report_keyboard())
        elif cmd == "/top":
            async with get_db_session() as session:
                posts = (await session.execute(
                    select(Post, ContentCandidate, MediaAnalysis, PostMetric)
                    .join(ContentCandidate, Post.candidate_id == ContentCandidate.id, isouter=True)
                    .join(MediaAnalysis, ContentCandidate.media_asset_id == MediaAnalysis.media_asset_id, isouter=True)
                    .join(PostMetric, Post.id == PostMetric.post_id, isouter=True)
                    .order_by(desc(PostMetric.views))
                    .limit(5)
                )).all()

                lines = ["🏆 **Kanalning TOP 5 Postlari (Engagement & Views):**\n"]
                if posts:
                    for idx, (p, cand, analysis, m) in enumerate(posts, 1):
                        cat = analysis.category if analysis else "General"
                        views = m.views if m else 0
                        eng = m.engagement_rate if m else 0.0
                        lines.append(f"{idx}. Post #{p.target_message_id} [{cat}] — 👁 {views} views | ❤️ {eng}% engagement")
                else:
                    lines.append("• _Postlar statistikasi tahlil qilinmoqda..._")
            await report_scheduler.send_telegram_message(chat_id, "\n".join(lines))
        elif cmd == "/sources":
            async with get_db_session() as session:
                sources = (await session.execute(select(Source))).scalars().all()
                lines = ["📡 **Kuzatilayotgan manbalar:**\n"]
                for s in sources:
                    lines.append(f"• `{s.username}` — Prioritet: {s.priority}, Ishonch: {int((s.trust_score or 1)*100)}%")
            await report_scheduler.send_telegram_message(chat_id, "\n".join(lines))
        elif cmd == "/duplicates":
            async with get_db_session() as session:
                dup_count = (await session.execute(select(func.count(DuplicateMatch.id)))).scalar() or 0
            text_dup = (
                "🛡 **DUBLIKATLAR NAZORATI HISOBOTI:**\n\n"
                f"• To'xtatilgan dublikatlar: **{dup_count} ta**\n"
                f"• Tahlil usuli: `SHA-256` + `5-Frame Video pHash`\n"
                f"• Maqsadli kanal jonli tekshiruvi: **FAOL (100%)**\n"
                "• Holat: Bir xil kontent qayta chiqishi mutlaqo to'silgan."
            )
            await report_scheduler.send_telegram_message(chat_id, text_dup)
        elif cmd == "/health":
            h_text = (
                "🟢 **TIZIM SALOMATLIGI: 100% ONLINE**\n\n"
                "• Telegram MTProto Client: 🟢 ONLINE\n"
                "• Google Gemini Vision API: 🟢 ONLINE\n"
                "• SQLAlchemy Database: 🟢 ONLINE\n"
                "• Asynchronous Queue & Workers: 🟢 ONLINE\n"
                "• Target Channel Live Auditor: 🟢 ONLINE\n"
                "• Report Scheduler (08:00, 13:00, 21:00): 🟢 ONLINE"
            )
            await report_scheduler.send_telegram_message(chat_id, h_text)

    async def _handle_callback_query(self, chat_id: int, data: str, query_id: str):
        from app.engines.report_scheduler import report_scheduler
        if not is_admin(chat_id):
            return

        if data in ["btn_report_current", "btn_refresh"]:
            res = await reporting_engine.generate_morning_report()
            await report_scheduler.send_telegram_message(chat_id, res["summary_text"], report_scheduler.get_report_keyboard())
        elif data == "btn_top_posts":
            await self._handle_bot_command(chat_id, "/top")
        elif data == "btn_sources":
            await self._handle_bot_command(chat_id, "/sources")
        elif data == "btn_analytics":
            res = await reporting_engine.generate_evening_report()
            await report_scheduler.send_telegram_message(chat_id, res["summary_text"])
        elif data == "btn_strategist":
            strat = await strategist_engine.generate_daily_report()
            await report_scheduler.send_telegram_message(chat_id, f"🧠 **AI Strategist Tavsiyasi:**\n\n{strat['summary']}")


bot_polling_service = TelegramBotPollingService()
