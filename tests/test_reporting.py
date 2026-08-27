import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app
from app.engines.reporting_engine import reporting_engine
from app.engines.report_scheduler import report_scheduler


@pytest.mark.asyncio
async def test_morning_report_generation():
    res = await reporting_engine.generate_morning_report()
    assert res["report_type"] == "MORNING"
    assert "summary_text" in res
    assert "TAMC MORNING REPORT" in res["summary_text"]
    assert "snapshot" in res


@pytest.mark.asyncio
async def test_midday_report_generation():
    res = await reporting_engine.generate_midday_report()
    assert res["report_type"] == "MIDDAY"
    assert "TAMC MIDDAY REPORT" in res["summary_text"]
    assert "snapshot" in res


@pytest.mark.asyncio
async def test_evening_report_generation():
    res = await reporting_engine.generate_evening_report()
    assert res["report_type"] == "EVENING"
    assert "TAMC EVENING PERFORMANCE REPORT" in res["summary_text"]
    assert "snapshot" in res


@pytest.mark.asyncio
async def test_traceability_not_found():
    res = await reporting_engine.get_content_traceability(999999)
    assert res["status"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_reports_api_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Reports History
        resp = await client.get("/api/reports/history")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

        # 2. Alerts
        resp_alerts = await client.get("/api/alerts")
        assert resp_alerts.status_code == 200
        assert isinstance(resp_alerts.json(), list)


def test_tashkent_time_offset():
    tashkent_time = report_scheduler.get_tashkent_time()
    assert tashkent_time is not None
