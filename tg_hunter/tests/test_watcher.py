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
