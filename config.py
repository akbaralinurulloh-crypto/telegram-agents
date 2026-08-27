import os
from pathlib import Path
from dotenv import load_dotenv

# .env faylini yuklash
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Telegram API sozlamalari
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "telegram_ai_agent")
TELEGRAM_SESSION_STRING = os.getenv("TELEGRAM_SESSION_STRING", "")

# Google Gemini API sozlamalari
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")


def clean_channel_username(ch: str) -> str:
    """https://t.me/kanal yoki @kanal ko'rinishidagi nomlarni tozalaydi."""
    ch = ch.strip()
    if ch.startswith("https://t.me/"):
        ch = ch.replace("https://t.me/", "")
    elif ch.startswith("http://t.me/"):
        ch = ch.replace("http://t.me/", "")
    elif ch.startswith("t.me/"):
        ch = ch.replace("t.me/", "")
    ch = ch.strip("/")
    if ch and not ch.startswith("@") and not ch.startswith("-100"):
        ch = f"@{ch}"
    return ch


# Kanallar sozlamalari
_raw_sources = os.getenv("SOURCE_CHANNELS", "@MuhtashamUmra, @Muhtasham_travel_Umra_sari")
SOURCE_CHANNELS = [clean_channel_username(ch) for ch in _raw_sources.split(",") if ch.strip()]

TARGET_CHANNEL = clean_channel_username(os.getenv("TARGET_CHANNEL", "@muhtashamtraveluzz"))

# AI tahlil va filtr sozlamalari
MIN_QUALITY_SCORE = int(os.getenv("MIN_QUALITY_SCORE", "6"))

# Kanal uslubi va mavzusi
CHANNEL_TOPIC = os.getenv(
    "CHANNEL_TOPIC",
    "Umra va Haj ziyorati, Makka va Madina ziyorat safari, manzaralar, ma'naviy fotolavhalar va foydali ma'lumotlar"
)

# Vaqtinchalik fayllar katalogi
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Baza fayli
DATABASE_PATH = BASE_DIR / "agent_database.sqlite"


def validate_config() -> list[str]:
    """Konfiguratsiya to'g'ri to'ldirilganligini tekshiradi."""
    errors = []
    if not TELEGRAM_API_ID or TELEGRAM_API_ID == 0:
        errors.append("TELEGRAM_API_ID belgilanmagan")
    if not TELEGRAM_API_HASH:
        errors.append("TELEGRAM_API_HASH belgilanmagan")
    if not GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY belgilanmagan")
    if not SOURCE_CHANNELS:
        errors.append("SOURCE_CHANNELS (manba kanallar) kiritilmagan")
    if not TARGET_CHANNEL:
        errors.append("TARGET_CHANNEL (maqsadli kanal) kiritilmagan")
    return errors
