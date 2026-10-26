"""Bir martalik: Telethon user session yaratadi (telefon + kod so'raydi)."""
import asyncio

from telethon import TelegramClient

from app.config import get_settings


async def main() -> None:
    s = get_settings()
    if not (s.tg_api_id and s.tg_api_hash):
        raise SystemExit("TG_API_ID / TG_API_HASH .env da yo'q")
    async with TelegramClient(s.tg_session_path, s.tg_api_id, s.tg_api_hash) as client:
        me = await client.get_me()
        print(f"OK: {me.first_name} (id={me.id}). Session: {s.tg_session_path}")


if __name__ == "__main__":
    asyncio.run(main())
