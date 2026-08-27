import asyncio
import httpx
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import logger
from app.core.database import get_db_session
from app.models.schema import Report, ReportSnapshot, Alert, ReportDeliveryLog
from app.engines.reporting_engine import reporting_engine


class ReportScheduler:
    """
    Asia/Tashkent vaqti bo'yicha 08:00, 13:00, 21:00 hisobotlarini
    idempotent ravishda yuboruvchi va alertlarni boshqaruvchi Scheduler.
    """

    def __init__(self):
        self.is_running = False
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.admin_ids = settings.ADMIN_TELEGRAM_IDS

    def get_tashkent_time(self) -> datetime:
        return datetime.utcnow() + timedelta(hours=5)

    async def send_telegram_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Telegram Bot API orqali xabar yuborish (Retry bilan)."""
        if not self.bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN sozlanmagan, hisobot yuborilmadi.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        delays = [1, 3, 5]
        for attempt in range(len(delays)):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        return True
                    elif resp.status_code == 400 and "can't parse" in resp.text:
                        # Markdown xatosi bo'lsa oddiy matn sifatida qayta yuborish
                        payload.pop("parse_mode", None)
                        retry_resp = await client.post(url, json=payload)
                        if retry_resp.status_code == 200:
                            return True
                    else:
                        logger.warning(f"Telegram API xatolik ({resp.status_code}): {resp.text}")
            except Exception as e:
                logger.warning(f"Hisobot yuborishda xatolik (Urinish {attempt+1}): {e}")
            await asyncio.sleep(delays[attempt])

        return False

    def get_report_keyboard(self) -> Dict[str, Any]:
        """Hisobot ostidagi interaktiv inline tugmalar."""
        return {
            "inline_keyboard": [
                [
                    {"text": "📊 Google Sheets", "url": "https://docs.google.com/spreadsheets/d/1aCLMLxsDDvAsXi1L9lVUhkFEOguXCsi_V13QikTB"},
                    {"text": "🏆 Top Postlar", "callback_data": "btn_top_posts"}
                ],
                [
                    {"text": "📈 Analitika", "callback_data": "btn_analytics"},
                    {"text": "🧠 AI Strategist", "callback_data": "btn_strategist"}
                ],
                [
                    {"text": "📡 Manbalar", "callback_data": "btn_sources"},
                    {"text": "🔄 Yangilash", "callback_data": "btn_refresh"}
                ]
            ]
        }

    async def dispatch_scheduled_report(self, report_type: str):
        """Rejalashtirilgan hisobotni barcha adminlarga yuboradi (Idempotent)."""
        now_tz = self.get_tashkent_time()
        date_str = now_tz.strftime("%Y-%m-%d")
        idempotency_key = f"{report_type.lower()}_{date_str}_{settings.REPORT_TIMEZONE.replace('/', '-')}"

        async with get_db_session() as session:
            # Idempotency tekshiruvi
            existing = (await session.execute(
                select(Report).where(Report.idempotency_key == idempotency_key)
            )).scalar_one_or_none()

            if existing and existing.status == "SENT":
                logger.info(f"⏭ [ReportScheduler] {idempotency_key} hisoboti allaqachon yuborilgan. O'tkazib yuborildi.")
                return

            # Hisobot generatsiya qilish
            if report_type == "MORNING":
                res = await reporting_engine.generate_morning_report(date_str)
            elif report_type == "MIDDAY":
                res = await reporting_engine.generate_midday_report()
            else:
                res = await reporting_engine.generate_evening_report()

            # Bazada saqlash
            report_obj = Report(
                report_type=report_type,
                report_date=date_str,
                idempotency_key=idempotency_key,
                timezone=settings.REPORT_TIMEZONE,
                summary_text=res["summary_text"],
                generation_time_ms=res["generation_time_ms"],
                status="GENERATING"
            )
            session.add(report_obj)
            await session.flush()

            snapshot_obj = ReportSnapshot(
                report_id=report_obj.id,
                data_snapshot=res["snapshot"]
            )
            session.add(snapshot_obj)
            await session.commit()
            report_id = report_obj.id

        # Har bir adminga yuborish
        keyboard = self.get_report_keyboard()
        all_sent = True
        for admin_id in self.admin_ids:
            sent = await self.send_telegram_message(admin_id, res["summary_text"], keyboard)
            if not sent:
                all_sent = False

            async with get_db_session() as session:
                session.add(ReportDeliveryLog(
                    report_id=report_id,
                    recipient_id=admin_id,
                    status="SENT" if sent else "FAILED"
                ))
                await session.commit()

        async with get_db_session() as session:
            r = await session.get(Report, report_id)
            if r:
                r.status = "SENT" if all_sent else "FAILED"
                r.sent_at = datetime.utcnow()
                await session.commit()

        logger.info(f"✅ [ReportScheduler] {report_type} hisoboti muvaffaqiyatli tarqatildi (ID: {report_id})")

    async def send_alert(self, severity: str, alert_type: str, message: str, details: Dict[str, Any] = {}):
        """Tezkor xavf yoki muammo yuz berganda adminga bildirishnoma yuborish."""
        alert_text = (
            f"⚠️ **TAMC {severity.upper()} ALERT: {alert_type}**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{message}\n\n"
            f"⏱ _Vaqt: {self.get_tashkent_time().strftime('%H:%M:%S Asia/Tashkent')}_"
        )
        async with get_db_session() as session:
            session.add(Alert(
                severity=severity,
                alert_type=alert_type,
                message=message,
                details=details
            ))
            await session.commit()

        for admin_id in self.admin_ids:
            await self.send_telegram_message(admin_id, alert_text)

    async def start(self):
        """Background hisobot tsikli."""
        self.is_running = True
        logger.info(f"⏰ [ReportScheduler] Avtomatik hisobotchi faollashdi ({settings.REPORT_TIMEZONE}: 08:00, 13:00, 21:00)")

        while self.is_running:
            try:
                now = self.get_tashkent_time()
                time_str = now.strftime("%H:%M")

                if time_str == settings.MORNING_REPORT_TIME:
                    await self.dispatch_scheduled_report("MORNING")
                    await asyncio.sleep(65)
                elif time_str == settings.MIDDAY_REPORT_TIME:
                    await self.dispatch_scheduled_report("MIDDAY")
                    await asyncio.sleep(65)
                elif time_str == settings.EVENING_REPORT_TIME:
                    await self.dispatch_scheduled_report("EVENING")
                    await asyncio.sleep(65)

                await asyncio.sleep(25)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ReportScheduler tsiklida xatolik: {e}")
                await asyncio.sleep(30)


report_scheduler = ReportScheduler()
