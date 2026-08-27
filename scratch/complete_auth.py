import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
from telethon import TelegramClient
from telethon.sessions import StringSession
from app.core.config import settings

STATE_FILE = Path("scratch/auth_state.json")
CODE = "60251"

async def main():
    if not STATE_FILE.exists():
        print("ERROR_NO_STATE")
        return
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    
    phone = state["phone"]
    phone_code_hash = state["phone_code_hash"]
    saved_session = state["session_string"]

    client = TelegramClient(StringSession(saved_session), settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH)
    await client.connect()
    
    try:
        user = await client.sign_in(phone=phone, code=CODE, phone_code_hash=phone_code_hash)
        new_session_string = client.session.save()
        print(f"SUCCESS_AUTH_STRING:{new_session_string}")
    except Exception as e:
        print(f"AUTH_ERROR:{e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
