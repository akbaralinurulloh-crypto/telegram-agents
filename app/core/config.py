import os
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


def clean_channel_username(ch: str) -> str:
    """Telegram kanal nomini tozalaydi."""
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


class Settings(BaseModel):
    # Asosiy yo'llar
    BASE_DIR: Path = BASE_DIR
    DOWNLOAD_DIR: Path = BASE_DIR / "downloads"
    STORAGE_DIR: Path = BASE_DIR / "storage_data"

    # Telegram sozlamalari
    TELEGRAM_API_ID: int = Field(default_factory=lambda: int(os.getenv("TELEGRAM_API_ID", "0")))
    TELEGRAM_API_HASH: str = Field(default_factory=lambda: os.getenv("TELEGRAM_API_HASH", ""))
    TELEGRAM_SESSION_NAME: str = Field(default_factory=lambda: os.getenv("TELEGRAM_SESSION_NAME", "telegram_ai_agent"))
    TELEGRAM_SESSION_STRING: str = Field(default_factory=lambda: os.getenv("TELEGRAM_SESSION_STRING", ""))
    
    # Kanallar
    SOURCE_CHANNELS: List[str] = Field(default_factory=lambda: [
        clean_channel_username(ch) for ch in os.getenv(
            "SOURCE_CHANNELS", "@MuhtashamUmra, @Muhtasham_travel_Umra_sari, @muhtashamtravel, @nurlisafar"
        ).split(",") if ch.strip()
    ])
    TARGET_CHANNEL: str = Field(default_factory=lambda: clean_channel_username(os.getenv("TARGET_CHANNEL", "@muhtashamtraveluzz")))
    
    # Google Gemini AI
    GEMINI_API_KEY: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    GEMINI_MODEL: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.6-flash"))
    FALLBACK_MODELS: List[str] = ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-flash-latest"]
    
    # Mavzu va filtrlar
    CHANNEL_TOPIC: str = Field(default_factory=lambda: os.getenv(
        "CHANNEL_TOPIC",
        "Umra va Haj ziyorati, Makka va Madina muqaddas shaharlari, ziyorat safari, manzaralar, ma'naviy fotolavhalar va foydali ma'lumotlar"
    ))
    MIN_QUALITY_SCORE: int = Field(default_factory=lambda: int(os.getenv("MIN_QUALITY_SCORE", "6")))
    
    # Ma'lumotlar bazasi (SQLite yoki PostgreSQL)
    DATABASE_URL: str = Field(default_factory=lambda: os.getenv(
        "DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'agent_database.sqlite'}"
    ))
    
    # Navbat va Redis (ixtiyoriy, agar yo'q bo'lsa in-memory async navbat ishlatiladi)
    REDIS_URL: str = Field(default_factory=lambda: os.getenv("REDIS_URL", ""))
    
    # Storage provayder: "local" yoki "s3"
    STORAGE_PROVIDER: str = Field(default_factory=lambda: os.getenv("STORAGE_PROVIDER", "local"))
    S3_ENDPOINT: str = Field(default_factory=lambda: os.getenv("S3_ENDPOINT", ""))
    S3_ACCESS_KEY: str = Field(default_factory=lambda: os.getenv("S3_ACCESS_KEY", ""))
    S3_SECRET_KEY: str = Field(default_factory=lambda: os.getenv("S3_SECRET_KEY", ""))
    S3_BUCKET_NAME: str = Field(default_factory=lambda: os.getenv("S3_BUCKET_NAME", "telegram-media"))
    
    # Human in the Loop (Boshqaruv rejimi): MANUAL, SEMI_AUTO, AUTO
    GOVERNANCE_MODE: str = Field(default_factory=lambda: os.getenv("GOVERNANCE_MODE", "AUTO"))
    MIN_AUTO_CONFIDENCE: float = Field(default_factory=lambda: float(os.getenv("MIN_AUTO_CONFIDENCE", "0.85")))
    
    # Google Sheets Webhook integratsiyasi
    GOOGLE_SHEETS_WEBHOOK_URL: str = Field(default_factory=lambda: os.getenv("GOOGLE_SHEETS_WEBHOOK_URL", ""))
    
    # Admin Telegram Bot va Xabarnomalar
    TELEGRAM_BOT_TOKEN: str = Field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    ADMIN_TELEGRAM_IDS: List[int] = Field(default_factory=lambda: [
        int(x.strip()) for x in os.getenv("ADMIN_TELEGRAM_IDS", "240409213, 7558601798").split(",") if x.strip().isdigit()
    ])
    
    # Hisobot vaqtlari (Asia/Tashkent)
    REPORT_TIMEZONE: str = Field(default_factory=lambda: os.getenv("REPORT_TIMEZONE", "Asia/Tashkent"))
    MORNING_REPORT_TIME: str = Field(default_factory=lambda: os.getenv("MORNING_REPORT_TIME", "08:00"))
    MIDDAY_REPORT_TIME: str = Field(default_factory=lambda: os.getenv("MIDDAY_REPORT_TIME", "13:00"))
    EVENING_REPORT_TIME: str = Field(default_factory=lambda: os.getenv("EVENING_REPORT_TIME", "21:00"))
    SEND_MISSED_REPORTS: bool = Field(default_factory=lambda: os.getenv("SEND_MISSED_REPORTS", "false").lower() == "true")

    # Smart Scheduler sozlamalari
    MIN_POST_INTERVAL_MINUTES: int = Field(default_factory=lambda: int(os.getenv("MIN_POST_INTERVAL_MINUTES", "45")))
    MAX_DAILY_POSTS: int = Field(default_factory=lambda: int(os.getenv("MAX_DAILY_POSTS", "12")))
    ACTIVE_HOURS_START: int = Field(default_factory=lambda: int(os.getenv("ACTIVE_HOURS_START", "7")))
    ACTIVE_HOURS_END: int = Field(default_factory=lambda: int(os.getenv("ACTIVE_HOURS_END", "23")))
    
    # Server portlari
    PORT: int = Field(default_factory=lambda: int(os.getenv("PORT", "10000")))
    API_PORT: int = Field(default_factory=lambda: int(os.getenv("API_PORT", "8000")))


settings = Settings()

# Kataloglarni yaratish
settings.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
