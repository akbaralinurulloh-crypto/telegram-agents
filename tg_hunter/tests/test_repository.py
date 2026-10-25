from datetime import datetime, timezone

from app.db.repository import NormalizedUnit

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def unit(ids=(10,), text="salom", cid=-100500, grouped=None, kinds=()):
    return NormalizedUnit(cid, "Src", list(ids), grouped, text, list(kinds), NOW)


async def test_add_is_idempotent(repo):
    u1, created1 = await repo.add_unit(unit())
    u2, created2 = await repo.add_unit(unit())
    assert created1 and not created2 and u1.id == u2.id
    assert await repo.audit_events(u1.id) == ["received"]


async def test_same_message_id_in_other_channel_is_separate(repo):
    a, _ = await repo.add_unit(unit(cid=-1))
    b, created = await repo.add_unit(unit(cid=-2))
    assert created and a.id != b.id


async def test_edit_updates_text_and_audits(repo):
    u, _ = await repo.add_unit(unit())
    res = await repo.mark_edited(-100500, 10, "yangi")
    assert res.text_changed and res.unit.text == "yangi"
    assert (await repo.get_unit(u.id)).edited_at is not None
    assert await repo.audit_events(u.id) == ["received", "edited"]


async def test_edit_unknown_message_returns_none(repo):
    assert await repo.mark_edited(-100500, 999, "x") is None


async def test_album_edit_without_caption_keeps_caption(repo):
    u, _ = await repo.add_unit(unit(ids=(1, 2, 3), text="sarlavha", grouped=7, kinds=["photo"] * 3))
    res = await repo.mark_edited(-100500, 2, "")
    assert not res.text_changed
    assert (await repo.get_unit(u.id)).text == "sarlavha"
    assert (await repo.mark_edited(-100500, 1, "yangi sarlavha")).text_changed


async def test_single_message_caption_removed_is_a_change(repo):
    u, _ = await repo.add_unit(unit(text="eski"))
    assert (await repo.mark_edited(-100500, 10, "")).text_changed
    assert (await repo.get_unit(u.id)).text == ""


async def test_delete_marks_once_and_respects_channel(repo):
    u, _ = await repo.add_unit(unit(ids=(1, 2)))
    assert await repo.mark_deleted([1], channel_id=-999) == []
    assert [x.id for x in await repo.mark_deleted([1, 2], channel_id=-100500)] == [u.id]
    assert await repo.mark_deleted([1], channel_id=-100500) == []  # ikkinchi marta ogohlantirish yo'q
    assert await repo.audit_events(u.id) == ["received", "deleted"]
