import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
from telethon import TelegramClient
from telethon.sessions import StringSession
from app.core.config import settings

PHONE_NUMBER = "+998888327700"
STATE_FILE = Path("scratch/auth_state.json")

async def main():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(StringSession(), settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH)
    await client.connect()
    
    res = await client.send_code_request(PHONE_NUMBER)
    state = {
        "phone": PHONE_NUMBER,
        "phone_code_hash": res.phone_code_hash,
        "session_string": client.session.save()
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)
    
    print(f"CODE_SENT_SUCCESS:{res.phone_code_hash}")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
