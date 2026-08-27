import pytest
from httpx import AsyncClient, ASGITransport
from app.api.app import app


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ONLINE"
        assert "services" in data


@pytest.mark.asyncio
async def test_overview_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/overview")
        assert response.status_code == 200
        data = response.json()
        assert "collected_today" in data
        assert "governance_mode" in data


@pytest.mark.asyncio
async def test_sources_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/sources")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


@pytest.mark.asyncio
async def test_dna_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/dna")
        assert response.status_code == 200
        data = response.json()
        assert "channel" in data
        assert "top_categories" in data


@pytest.mark.asyncio
async def test_export_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/reports/export")
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
