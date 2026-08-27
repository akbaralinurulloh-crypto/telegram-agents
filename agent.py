import os
import sys
import asyncio
import logging
import uvicorn
from pathlib import Path

# Windows UTF-8 qo'llab-quvvatlash
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from telethon import TelegramClient, events
from telethon.tl.types import ChannelParticipantAdmin, ChannelParticipantCreator
from telethon.tl.functions.channels import GetParticipantRequest

import config
import database
from app.core.config import settings
from app.core.logging import logger
from app.core.database import init_db
from app.core.queue import queue_manager
from app.collectors.telegram_collector import collector, is_photo_media, is_video_media
from app.bot.admin_bot import register_admin_bot_handlers
from app.engines.analytics import analytics_engine
from app.engines.strategist import strategist_engine
from app.api.app import app as fastapi_app


async def start_web_server():
    """FastAPI REST API, Control Center Dashboard va Render Health-Check serveri."""
    port = int(os.getenv("PORT", str(settings.PORT)))
    config_uvicorn = uvicorn.Config(
        app=fastapi_app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False
    )
    server = uvicorn.Server(config_uvicorn)
    logger.info(f"🌐 Autonomous AI Control Center & API {port}-portda ishga tushdi: http://0.0.0.0:{port}")
    return asyncio.create_task(server.serve())


async def scan_recent_messages(limit: int = 50):
    """Manba kanallardagi oxirgi postlarni skaner qilish va saralash."""
    logger.info(f"🔍 Manba kanallardagi oxirgi {limit} ta post tekshirilmoqda...")
    for source in settings.SOURCE_CHANNELS:
        try:
            entity = await collector.client.get_entity(source)
            messages = await collector.client.get_messages(entity, limit=limit)
            for msg in reversed(messages):
                if msg.media:
                    await collector.ingest_message(msg, source)
        except Exception as e:
            logger.error(f"Kanalni skaner qilishda xatolik ({source}): {e}")


from app.engines.target_auditor import target_auditor


async def periodic_analytics_loop():
    """Har 10 daqiqada maqsadli kanalni chuqur tahlil qilish va statistikani yangilash."""
    while True:
        try:
            await asyncio.sleep(600)  # 10 daqiqa
            logger.info("🔍 [Auditor] Maqsadli kanal (@muhtashamtraveluzz) davriy chuqur tahlil qilinmoqda...")
            await target_auditor.scan_and_analyze_target_channel(collector.client, limit=50)
            await analytics_engine.collect_post_metrics(collector.client, limit=20)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Davriy tahlilda xatolik: {e}")


async def main():
    logger.info("=================================================================")
    logger.info("🤖 AUTONOMOUS TELEGRAM AI MEDIA CREATOR & INTELLIGENCE PLATFORM")
    logger.info("=================================================================")

    # 1. Web serverni ishga tushirish (Dashboard, REST API & Render Health-Check)
    web_task = await start_web_server()

    # 2. Ma'lumotlar bazasini initsializatsiya qilish
    await init_db()
    stats = await database.get_stats()
    logger.info(f"📊 Baza tayyor. Oldingi statistika: {stats}")

    # 3. Telegram Collector va mijozini ishga tushirish (Handlerlar ulanishi uchun)
    await collector.initialize()

    # 4. Asinxron ko'p bosqichli navbat tizimini boshlash
    await queue_manager.start()

    # 5. Admin Telegram Bot buyruqlarini ulash
    register_admin_bot_handlers(collector.client)

    # 6. Kanal va adminlik huquqlarini tekshirish
    me = await collector.client.get_me()
    try:
        target_entity = await collector.client.get_entity(settings.TARGET_CHANNEL)
        logger.info(f"✅ Maqsadli kanal topildi: {settings.TARGET_CHANNEL} (Title: {getattr(target_entity, 'title', '')})")
        
        try:
            p = await collector.client(GetParticipantRequest(channel=target_entity, participant=me))
            if not isinstance(p.participant, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                logger.warning(f"⚠️ OGOHLANTIRISH: @{getattr(me, 'username', me.id)} maqsadli kanalda Admin emas!")
        except Exception:
            logger.warning(f"⚠️ OGOHLANTIRISH: Telegram akkauntingiz maqsadli kanalda Administrator emas!")
    except Exception as e:
        logger.error(f"❌ Maqsadli kanalga ulanib bo'lmadi ({settings.TARGET_CHANNEL}): {e}")

    # 7. Maqsadli kanalni (@muhtashamtraveluzz) chuqur skanerlab xotiraga olish va dublikatlar bazasini to'ldirish
    await target_auditor.scan_and_analyze_target_channel(collector.client, limit=100)
    await collector.sync_target_channel_history(limit=50)

    # 8. Real-vaqt tinglovchisini boshlash
    await collector.start_listening()

    # 9. Manba kanallardagi oldingi eng so'nggi postlarni ham tahlil qilib kanalga saralash
    await collector.scan_and_process_recent_source_messages(limit=15)

    # 9. Davriy analitika va Avtomatik Hisobotchi (08:00, 13:00, 21:00) vazifalarini boshlash
    from app.engines.report_scheduler import report_scheduler
    from app.bot.admin_bot import bot_polling_service
    
    analytics_task = asyncio.create_task(periodic_analytics_loop())
    report_task = asyncio.create_task(report_scheduler.start())
    bot_task = asyncio.create_task(bot_polling_service.start())

    logger.info("🟢 TIZIM TO'LIQ ISHGA TUSHDI VA 24/7 AVTOPILOT REJIMIDA FAOL!")
    
    try:
        await collector.client.run_until_disconnected()
    finally:
        await queue_manager.stop()
        analytics_task.cancel()
        report_task.cancel()
        bot_task.cancel()
        web_task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Dastur foydalanuvchi tomonidan to'xtatildi.")
