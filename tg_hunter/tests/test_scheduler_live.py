"""Real vaqtda: jadval haqiqatan belgilangan daqiqada hisobotni yuboradimi. ~1-2 daqiqa: faqat RUN_SLOW=1 bo'lganda ishlaydi."""
import asyncio
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.reports.scheduler import ReportService

pytestmark = pytest.mark.skipif(not os.environ.get("RUN_SLOW"), reason="sekin test: RUN_SLOW=1")


async def test_scheduler_really_fires_the_report(repo):
    tz = ZoneInfo("Asia/Tashkent")
    slot = (datetime.now(tz) + timedelta(minutes=1)).strftime("%H:%M")
    sent: list[str] = []

    async def send(text):
        sent.append(text)

    svc = ReportService(repo, send, slots=[slot], tz="Asia/Tashkent", target="@k", sources=["@a"])
    sch = svc.start()
    try:
        deadline = time.monotonic() + 110
        while not sent and time.monotonic() < deadline:
            await asyncio.sleep(1)
    finally:
        sch.shutdown(wait=False)
    assert sent, "hisobot belgilangan vaqtda yuborilmadi"
    assert "HISOBOT" in sent[0].upper() and "Asia/Tashkent" in sent[0]
    assert not await repo.unsent_reports()  # yuborildi deb belgilangan
