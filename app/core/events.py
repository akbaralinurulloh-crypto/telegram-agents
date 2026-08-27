import asyncio
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from sqlalchemy import select, desc

from app.core.logging import logger
from app.core.database import get_db_session
from app.models.schema import AnalyticsEvent


class AnalyticsEventBus:
    """Tizim bo'ylab barcha hodisalarni yozib boruvchi va WebSocket/Dashboard ga tarqatuvchi markaziy Bus."""

    def __init__(self):
        self._subscribers: List[asyncio.Queue] = []
        self._recent_events: List[Dict[str, Any]] = []

    async def emit(self, event_type: str, entity_id: Optional[Any] = None, source: Optional[str] = None, metadata: Dict[str, Any] = {}):
        now_iso = datetime.utcnow().isoformat()
        event_dict = {
            "event_type": event_type,
            "entity_id": str(entity_id) if entity_id is not None else None,
            "source": source or "system",
            "metadata": metadata,
            "timestamp": now_iso
        }

        # Tezkor xotirada saqlash
        self._recent_events.append(event_dict)
        if len(self._recent_events) > 100:
            self._recent_events.pop(0)

        # Bazaga yozish (asinxron fonda)
        asyncio.create_task(self._persist_to_db(event_type, str(entity_id) if entity_id else None, source, metadata))

        # Obunachilarga (WebSocket/SSE) tarqatish
        for q in self._subscribers:
            try:
                await q.put(event_dict)
            except Exception:
                pass

        logger.debug(f"⚡️ [EventBus] {event_type} (Entity: {entity_id})")

    async def _persist_to_db(self, event_type: str, entity_id: Optional[str], source: Optional[str], metadata: Dict[str, Any]):
        try:
            async with get_db_session() as session:
                ev = AnalyticsEvent(
                    event_type=event_type,
                    entity_id=entity_id,
                    source=source,
                    metadata_json=metadata
                )
                session.add(ev)
                await session.commit()
        except Exception as e:
            logger.debug(f"Event saqlashda xatolik: {e}")

    def get_recent_events(self, limit: int = 30) -> List[Dict[str, Any]]:
        return self._recent_events[-limit:]


event_bus = AnalyticsEventBus()
