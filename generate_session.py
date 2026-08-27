import sys
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
import config

# Windows UTF-8 qo'llab-quvvatlash
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


async def main():
    print("==================================================")
    print("🔑 TELEGRAM SESSION STRING GENERATOR (Cloud uchun)")
    print("==================================================")
    print("Ushbu skript Render / Cloud server uchun xavfsiz kalit (Session String) yaratadi.\n")

    if not config.TELEGRAM_API_ID or not config.TELEGRAM_API_HASH:
        print("❌ Xatolik: .env faylida TELEGRAM_API_ID yoki TELEGRAM_API_HASH topilmadi!")
        return

    client = TelegramClient(StringSession(), config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)
    await client.start()  # type: ignore


    session_string = client.session.save()
    print("\n✅ MUVAFFAQITYATLI KIRILDI!")
    print("--------------------------------------------------")
    print("📋 SIZNING TELEGRAM_SESSION_STRING KALITINGIZ:")
    print("--------------------------------------------------")
    print(session_string)
    print("--------------------------------------------------")
    print("\n💡 Ushbu uzun kodni nusxalab, Render.com saytidagi 'Environment Variables' bo'limiga:")
    print("Key: TELEGRAM_SESSION_STRING")
    print("Value: (yuqoridagi uzun kod) ko'rinishida qo'shing.")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(main())
