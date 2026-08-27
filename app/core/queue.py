import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Callable, Awaitable, Optional, List
from app.core.config import settings
from app.core.logging import logger


class TaskMessage:
    def __init__(self, task_type: str, payload: Dict[str, Any], attempt: int = 1, max_retries: int = 4):
        self.task_type = task_type
        self.payload = payload
        self.attempt = attempt
        self.max_retries = max_retries
        self.created_at = datetime.utcnow().isoformat()
        self.error_history: List[str] = []


class UnifiedQueue:
    """Asinxron ko'p bosqichli navbat tizimi (In-Memory + Redis/Distributed tayyor)."""

    def __init__(self):
        self._queues: Dict[str, asyncio.Queue] = {}
        self._handlers: Dict[str, List[Callable[[TaskMessage], Awaitable[None]]]] = {}
        self._dlq: List[TaskMessage] = []
        self._is_running = False
        self._workers: List[asyncio.Task] = []
        self.retry_delays = [5, 15, 60, 300]  # sekundlar

        self._active_worker_types: set = set()

    def get_queue(self, task_type: str) -> asyncio.Queue:
        if task_type not in self._queues:
            self._queues[task_type] = asyncio.Queue()
        return self._queues[task_type]

    async def enqueue(self, task_type: str, payload: Dict[str, Any], max_retries: int = 4):
        msg = TaskMessage(task_type=task_type, payload=payload, max_retries=max_retries)
        q = self.get_queue(task_type)
        await q.put(msg)
        logger.debug(f"📥 [{task_type}] Navbatga qo'shildi: {payload.get('source_name', payload.get('source_channel', ''))} (Navbat uzunligi: {q.qsize()})")

    def register_handler(self, task_type: str, handler: Callable[[TaskMessage], Awaitable[None]]):
        if task_type not in self._handlers:
            self._handlers[task_type] = []
        self._handlers[task_type].append(handler)
        
        # Agar navbat allaqachon ishlayotgan bo'lsa va bu task_type uchun worker yo'q bo'lsa, darhol worker boshlash
        if self._is_running and task_type not in self._active_worker_types:
            task = asyncio.create_task(self._worker_loop(task_type))
            self._workers.append(task)
            self._active_worker_types.add(task_type)
            logger.info(f"⚡️ [{task_type}] Yangi worker dinamik ishga tushirildi.")

    async def _worker_loop(self, task_type: str):
        q = self.get_queue(task_type)
        while self._is_running:
            try:
                msg: TaskMessage = await q.get()
                handlers = self._handlers.get(task_type, [])
                
                success = False
                for h in handlers:
                    try:
                        await h(msg)
                        success = True
                    except Exception as e:
                        logger.error(f"❌ Worker xatosi [{task_type}] (urinish {msg.attempt}/{msg.max_retries}): {e}", exc_info=True)
                        msg.error_history.append(str(e))
                        
                        if msg.attempt < msg.max_retries:
                            delay = self.retry_delays[min(msg.attempt - 1, len(self.retry_delays) - 1)]
                            logger.info(f"⏳ [{task_type}] {delay} soniyadan so'ng qayta uriniladi...")
                            msg.attempt += 1
                            
                            # Kechiktirilgan qayta qo'shish
                            asyncio.create_task(self._delayed_requeue(task_type, msg, delay))
                        else:
                            logger.critical(f"💀 [{task_type}] Maksimal urinishlar tugadi. Dead Letter Queue (DLQ) ga jo'natilmoqda.")
                            self._dlq.append(msg)
                
                q.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker siklida kutilmagan xatolik: {e}")
                await asyncio.sleep(1)

    async def _delayed_requeue(self, task_type: str, msg: TaskMessage, delay: int):
        await asyncio.sleep(delay)
        await self.get_queue(task_type).put(msg)

    async def start(self):
        self._is_running = True
        for task_type in list(self._handlers.keys()):
            if task_type not in self._active_worker_types:
                task = asyncio.create_task(self._worker_loop(task_type))
                self._workers.append(task)
                self._active_worker_types.add(task_type)
        logger.info(f"🚀 Navbat tizimi ishga tushdi ({len(self._workers)} ta worker faol).")

    async def stop(self):
        self._is_running = False
        for t in self._workers:
            t.cancel()
        logger.info("🛑 Navbat tizimi to'xtatildi.")

    def get_stats(self) -> Dict[str, Any]:
        stats = {t: q.qsize() for t, q in self._queues.items()}
        stats["dlq_count"] = len(self._dlq)
        return stats


queue_manager = UnifiedQueue()
