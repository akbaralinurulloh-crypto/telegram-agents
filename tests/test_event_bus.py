import pytest
from app.core.events import event_bus
from app.models.schema import AnalyticsEvent
from app.core.database import get_db_session
from sqlalchemy import select


@pytest.mark.asyncio
async def test_event_bus_emission_and_retrieval():
    # Hodisa chiqarish
    await event_bus.emit(
        event_type="TEST_PIPELINE_EVENT",
        entity_id="test_candidate_999",
        source="@test_source",
        metadata={"quality_score": 95, "status": "APPROVED"}
    )

    # Tezkor xotiradan olish
    recent = event_bus.get_recent_events(limit=5)
    assert len(recent) > 0
    last_event = recent[-1]
    assert last_event["event_type"] == "TEST_PIPELINE_EVENT"
    assert last_event["entity_id"] == "test_candidate_999"
    assert last_event["source"] == "@test_source"
    assert last_event["metadata"]["quality_score"] == 95


@pytest.mark.asyncio
async def test_event_persistence_in_db():
    await event_bus.emit(
        event_type="MEDIA_COLLECTED_PERSIST",
        entity_id="msg_12345",
        source="@MuhtashamUmra",
        metadata={"format": "video"}
    )

    # 100ms kutiladi asinxron DB task uchun
    import asyncio
    await asyncio.sleep(0.2)

    async with get_db_session() as session:
        events = (await session.execute(
            select(AnalyticsEvent).where(AnalyticsEvent.event_type == "MEDIA_COLLECTED_PERSIST")
        )).scalars().all()
        assert len(events) >= 1
        assert events[-1].entity_id == "msg_12345"
        assert events[-1].source == "@MuhtashamUmra"
