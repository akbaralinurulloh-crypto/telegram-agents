from __future__ import annotations

from telethon import TelegramClient, events, utils

from app.config import AppConfig, Settings
from app.db.repository import Repository
from app.utils.logging import get_logger
from app.watcher.normalize import normalize

log = get_logger("watcher")


def build_client(settings: Settings, cfg: AppConfig) -> TelegramClient:
    return TelegramClient(
        settings.tg_session_path,
        settings.tg_api_id,
        settings.tg_api_hash,
        connection_retries=-1,  # tarmoq uzilsa cheksiz qayta ulanadi
        retry_delay=5,
        auto_reconnect=True,
        flood_sleep_threshold=60,  # <60s FloodWait'ni Telethon o'zi kutadi
        catch_up=cfg.watcher.catch_up,
    )


def _parse(ref: str) -> int | str:
    return int(ref) if ref.lstrip("-").isdigit() else ref


class Watcher:
    """Manba kanallarni FAQAT o'qiydi: DB va logga yozadi, hech narsa yubormaydi."""

    def __init__(self, client: TelegramClient, repo: Repository, sources: list[str]):
        self.client = client
        self.repo = repo
        self.source_refs = sources
        self.source_ids: set[int] = set()
        self.titles: dict[int, str] = {}

    async def resolve_sources(self) -> None:
        for ref in self.source_refs:
            try:
                entity = await self.client.get_entity(_parse(ref))
            except Exception as exc:
                raise RuntimeError(f"Manba kanal topilmadi yoki a'zo emassiz: {ref!r} ({exc})") from exc
            cid = utils.get_peer_id(entity)
            self.source_ids.add(cid)
            self.titles[cid] = getattr(entity, "title", None) or str(ref)
            log.info("source_resolved", ref=ref, channel_id=cid, title=self.titles[cid])

    def register(self) -> None:
        self.client.add_event_handler(self.on_message, events.NewMessage())
        self.client.add_event_handler(self.on_album, events.Album())
        self.client.add_event_handler(self.on_edit, events.MessageEdited())
        self.client.add_event_handler(self.on_delete, events.MessageDeleted())

    def _is_source(self, chat_id: int | None) -> bool:
        return chat_id is not None and chat_id in self.source_ids

    async def _ingest(self, messages: list, chat_id: int) -> None:
        unit = normalize(messages, chat_id, self.titles.get(chat_id, ""))
        row, created = await self.repo.add_unit(unit)
        log.info(
            "unit_received" if created else "unit_duplicate_event",
            unit_id=row.id,
            channel=self.titles.get(chat_id),
            messages=unit.message_ids,
            media=unit.media_kinds,
            text_preview=unit.text[:80],
        )

    async def on_message(self, event) -> None:
        if not self._is_source(event.chat_id) or event.message.grouped_id:
            return  # albomni on_album yig'adi
        await self._ingest([event.message], event.chat_id)

    async def on_album(self, event) -> None:
        if self._is_source(event.chat_id):
            await self._ingest(list(event.messages), event.chat_id)

    async def on_edit(self, event) -> None:
        if not self._is_source(event.chat_id):
            return
        res = await self.repo.mark_edited(event.chat_id, event.message.id, (event.message.message or "").strip())
        if res is None:
            return
        log.info("unit_edited", unit_id=res.unit.id, text_changed=res.text_changed, state=res.unit.state)
        if res.unit.state == "posted":
            log.warning("posted_unit_edited_at_source", unit_id=res.unit.id)  # keyingi bosqichda botga ogohlantirish

    async def on_delete(self, event) -> None:
        if not self._is_source(event.chat_id):
            return  # kanal o'chirishlarida chat_id keladi; boshqa chatlarni e'tiborsiz qoldiramiz
        for unit in await self.repo.mark_deleted(list(event.deleted_ids), event.chat_id):
            log.info("unit_deleted", unit_id=unit.id, state=unit.state)
            if unit.state == "posted":
                log.warning("posted_unit_deleted_at_source", unit_id=unit.id)
