from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest

from app.watcher.listener import Watcher
from app.watcher.normalize import media_kind, normalize

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
CID = -1001


def msg(id, text="", grouped=None, **media):
    return NS(id=id, message=text, grouped_id=grouped, date=NOW, **media)


def test_media_kinds():
    assert media_kind(msg(1)) is None
    assert media_kind(msg(1, photo=object())) == "photo"
    assert media_kind(msg(1, video=object())) == "video"
    assert media_kind(msg(1, document=object())) == "document"
    assert media_kind(msg(1, sticker=object(), document=object())) == "sticker"


def test_normalize_album_picks_caption_and_sorts():
    u = normalize([msg(3, photo=1, grouped=9), msg(1, "izoh", grouped=9, photo=1), msg(2, video=1, grouped=9)], CID, "T")
    assert u.message_ids == [1, 2, 3]
    assert u.text == "izoh"
    assert u.media_kinds == ["photo", "video", "photo"]
    assert u.grouped_id == 9


@pytest.fixture
def watcher(repo):
    w = Watcher(client=None, repo=repo, sources=[])
    w.source_ids = {CID}
    w.titles = {CID: "Src"}
    return w


def ev(chat_id, message=None, **kw):
    return NS(chat_id=chat_id, message=message, **kw)


async def test_message_from_non_source_is_ignored(watcher, repo):
    await watcher.on_message(ev(-777, msg(5, "x")))
    assert await repo.mark_edited(-777, 5, "y") is None


async def test_album_not_double_ingested(watcher, repo):
    album_msgs = [msg(1, "a", 9, photo=1), msg(2, "", 9, photo=1)]
    for m in album_msgs:  # NewMessage har bir albom xabari uchun ham keladi
        await watcher.on_message(ev(CID, m))
    assert await repo.mark_edited(CID, 1, "a") is None  # hali ingest qilinmagan
    await watcher.on_album(ev(CID, messages=album_msgs))
    await watcher.on_album(ev(CID, messages=album_msgs))  # takror hodisa
    res = await repo.mark_edited(CID, 2, "")
    assert res is not None and len(res.unit.messages) == 2


async def test_edit_and_delete_flow(watcher, repo):
    await watcher.on_message(ev(CID, msg(5, "eski", photo=1)))
    await watcher.on_edit(ev(CID, msg(5, "yangi")))
    await watcher.on_delete(ev(CID, deleted_ids=[5]))
    unit_id = (await repo.mark_edited(CID, 5, "yangi")).unit.id
    assert await repo.audit_events(unit_id) == ["received", "edited", "deleted", "edited"]


async def test_delete_without_chat_id_is_ignored(watcher, repo):
    await watcher.on_message(ev(CID, msg(5, "x")))
    await watcher.on_delete(ev(None, deleted_ids=[5]))
    assert (await repo.mark_deleted([5], CID)) != []  # hali o'chirilmagan edi


# ---------- guruh va kanal ----------
def make_channel(cid, title, broadcast):
    from telethon.tl.types import Channel, ChatPhotoEmpty

    return Channel(id=cid, title=title, photo=ChatPhotoEmpty(), date=NOW, broadcast=broadcast, megagroup=not broadcast)


class FakeClient:
    def __init__(self, entities):
        self.entities = entities

    async def get_entity(self, ref):
        return self.entities[ref]


CH, GR = -1000000000111, -1000000000222  # Telethon marked ID: -(10**12) - id


async def resolved(repo, include_groups=False):
    client = FakeClient({"@kanal": make_channel(111, "Kanal", True), "@guruh": make_channel(222, "Guruh", False)})
    w = Watcher(client, repo, ["@kanal", "@guruh"], include_groups=include_groups)
    await w.resolve_sources()
    return w


async def test_resolve_detects_channel_vs_group(repo):
    w = await resolved(repo)
    assert w.kinds == {CH: "kanal", GR: "guruh"}
    assert w.ignored_groups() == ["Guruh (@guruh)"]
    text = "\n".join(w.describe())
    assert "Kanal (@kanal) — kanal" in text and "Guruh (@guruh) — guruh — O'TKAZIB YUBORILADI" in text


async def test_group_messages_are_ignored_by_default_but_channel_is_processed(repo):
    w = await resolved(repo)
    await w.on_message(ev(GR, msg(1, "guruhdagi oddiy yozishma")))
    await w.on_message(ev(CH, msg(1, "kanal posti")))
    assert await repo.mark_edited(GR, 1, "x") is None  # guruh xabari DB ga tushmagan
    assert await repo.mark_edited(CH, 1, "kanal posti") is not None


async def test_groups_can_be_enabled(repo):
    w = await resolved(repo, include_groups=True)
    assert w.ignored_groups() == []
    await w.on_message(ev(GR, msg(1, "guruhdagi yozishma")))
    assert await repo.mark_edited(GR, 1, "guruhdagi yozishma") is not None
    assert "O'TKAZIB" not in "\n".join(w.describe())
