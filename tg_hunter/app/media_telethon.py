from __future__ import annotations

from pathlib import Path

from app.db.models import SourceUnit
from app.pipeline.runner import MediaFile, Rejected
from app.watcher.normalize import media_kind


class TelethonMedia:
    """Manba kanaldan media yuklaydi (user session orqali)."""

    def __init__(self, client):
        self.client = client

    async def download(self, unit: SourceUnit, dest: Path, max_video_bytes: int) -> list[MediaFile]:
        msgs = [m for m in await self.client.get_messages(unit.channel_id, ids=[m.message_id for m in unit.messages]) if m]
        if not msgs:
            raise Rejected("rejected", "source_unavailable")
        files: list[MediaFile] = []
        for m in msgs:
            kind = media_kind(m)
            if kind is None:
                continue
            if kind not in ("photo", "video", "gif"):
                raise Rejected("rejected", "unsupported_media", kind=kind)
            if kind != "photo" and (getattr(m.file, "size", 0) or 0) > max_video_bytes:
                raise Rejected("rejected", "media_too_large", size=m.file.size)
            path = await self.client.download_media(m, file=str(dest))
            if not path:
                raise Rejected("rejected", "source_unavailable")
            files.append(MediaFile(Path(path), "photo" if kind == "photo" else "video"))
        return files
