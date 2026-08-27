import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Optional
import httpx

from app.core.config import settings
from app.core.logging import logger


class GoogleSheetsIntegration:
    """Google Sheets bilan real vaqtda avtomatik sinxronizatsiya qiluvchi engine."""

    def __init__(self):
        self.webhook_url = getattr(settings, "GOOGLE_SHEETS_WEBHOOK_URL", "")

    async def append_row(self, data: Dict[str, Any]):
        """
        Google Sheets jadvaliga yangi qator qo'shadi.
        
        Kutiladigan maydonlar:
        - timestamp
        - source_channel
        - source_message_id
        - media_type
        - category
        - final_score
        - status (POSTED / REJECTED / REVIEW)
        - reason
        - enhanced_caption
        """
        webhook = getattr(settings, "GOOGLE_SHEETS_WEBHOOK_URL", "")
        if not webhook:
            logger.debug("Google Sheets Webhook URL sozlanmagan, yozish o'tkazib yuborildi.")
            return

        payload = {
            "timestamp": data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "source_channel": data.get("source_channel", ""),
            "source_message_id": data.get("source_message_id", ""),
            "media_type": data.get("media_type", "media"),
            "category": data.get("category", "General"),
            "final_score": data.get("final_score", 0),
            "status": data.get("status", "NEW"),
            "reason": data.get("reason", ""),
            "caption": data.get("enhanced_caption", "")[:300] if data.get("enhanced_caption") else ""
        }

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.post(webhook, json=payload)
                if response.status_code in [200, 302]:
                    logger.info(f"📊 [Google Sheets] Yangi qator muvaffaqiyatli qo'shildi: {payload['source_channel']}:{payload['source_message_id']} ({payload['status']})")
                else:
                    logger.warning(f"Google Sheets ga yuborishda xatolik (HTTP {response.status_code}): {response.text}")
        except Exception as e:
            logger.warning(f"Google Sheets ga ma'lumot yuborishda xatolik: {e}")


google_sheets = GoogleSheetsIntegration()
