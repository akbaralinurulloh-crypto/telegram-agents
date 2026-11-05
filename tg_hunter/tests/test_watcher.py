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


# ---------- zaxira tekshiruv (push kelmasa ham postlar olinadi) ----------
from datetime import timedelta  # noqa: E402


class PollClient:
    def __init__(self, by_chat):
        self.by_chat, self.calls = by_chat, []

    async def get_messages(self, cid, limit=30):
        self.calls.append((cid, limit))
        return self.by_chat.get(cid, [])  # Telethon: eng yangisi birinchi


def pmsg(id, text="", ago_h=1, grouped=None, action=None, **media):
    m = msg(id, text, grouped, **media)
    m.date = datetime.now(timezone.utc) - timedelta(hours=ago_h)
    m.action = action
    return m


async def polling_watcher(repo, by_chat, include_groups=False):
    w = await resolved(repo, include_groups=include_groups)
    w.client = PollClient(by_chat)
    w.new_calls = []
    w.on_new_unit = lambda: w.new_calls.append(1)
    return w


SINCE = lambda: datetime.now(timezone.utc) - timedelta(hours=24)  # noqa: E731


async def test_poll_ingests_recent_posts_oldest_first_and_skips_old_and_service(repo):
    msgs = [pmsg(9, "Yangi post", 1), pmsg(8, "", 2, action=object()), pmsg(7, "Kecha emas, 30 soat oldingi", 30), pmsg(6, "", 3), pmsg(5, "Rasmli post", 4, photo=1)]
    w = await polling_watcher(repo, {CH: msgs})
    assert await w.poll_recent(SINCE()) == 2  # 9 va 5; xizmat xabari, eski va bo'sh xabar o'tkazib yuborildi
    assert w.new_calls == [1]
    assert await repo.mark_edited(CH, 5, "Rasmli post") is not None and await repo.mark_edited(CH, 9, "Yangi post") is not None
    assert await repo.mark_edited(CH, 7, "x") is None
    ids = [u.id for u in await repo.last_units(10)]  # last_units: yangisi birinchi
    assert (await repo.get_unit(min(ids))).text == "Rasmli post"  # eskisi birinchi qo'shilgan


async def test_poll_is_idempotent_and_does_not_duplicate_live_events(repo):
    w = await polling_watcher(repo, {CH: [pmsg(5, "Post matni", 1)]})
    await w.on_message(ev(CH, msg(5, "Post matni")))  # jonli hodisa allaqachon olgan
    before = len(w.new_calls)
    assert await w.poll_recent(SINCE()) == 0
    assert await w.poll_recent(SINCE()) == 0 and len(w.new_calls) == before  # zaxira tekshiruv takror signal bermaydi


async def test_poll_groups_album_into_one_unit(repo):
    msgs = [pmsg(12, "", 1, grouped=77, photo=1), pmsg(11, "Albom izohi", 1, grouped=77, photo=1), pmsg(10, "", 1, grouped=77, video=1)]
    w = await polling_watcher(repo, {CH: msgs})
    assert await w.poll_recent(SINCE()) == 1
    res = await repo.mark_edited(CH, 11, "Albom izohi")
    assert res is not None and [m.message_id for m in res.unit.messages] == [10, 11, 12]


async def test_poll_skips_ignored_group_but_polls_it_when_enabled(repo):
    by = {CH: [pmsg(1, "Kanal posti", 1)], GR: [pmsg(1, "Guruh yozishmasi", 1)]}
    w = await polling_watcher(repo, by)
    assert await w.poll_recent(SINCE()) == 1 and [c for c, _ in w.client.calls] == [CH]  # guruh so'ralmaydi ham
    w2 = await polling_watcher(repo, {GR: [pmsg(2, "Guruh yozishmasi", 1)]}, include_groups=True)
    assert await w2.poll_recent(SINCE()) == 1
