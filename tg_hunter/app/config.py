from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScoringWeights(BaseModel):
    topic_fit: float = 0.30
    quality: float = 0.25
    audience_interest: float = 0.25
    media_quality: float = 0.20

    @model_validator(mode="after")
    def _sum_to_one(self) -> "ScoringWeights":
        total = self.topic_fit + self.quality + self.audience_interest + self.media_quality
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"scoring.weights yig'indisi 1.0 bo'lishi shart, hozir {total}")
        return self


class ScoringCfg(BaseModel):
    min_score: float = Field(7.0, ge=0, le=10)
    weights: ScoringWeights = ScoringWeights()


class WatcherCfg(BaseModel):
    catch_up: bool = True


class CaptionCfg(BaseModel):
    max_length: int = Field(1024, gt=0, le=1024)
    max_attempts: int = Field(2, ge=1)


class KillSwitchCfg(BaseModel):
    max_consecutive_errors: int = Field(5, ge=1)


class AppConfig(BaseModel):
    timezone: str = "Asia/Tashkent"
    report_times: list[str] = ["08:00", "13:00", "20:00"]
    channel_topic: str = ""
    scoring: ScoringCfg = ScoringCfg()
    watcher: WatcherCfg = WatcherCfg()
    caption: CaptionCfg = CaptionCfg()
    banned_caption_keywords: list[str] = []
    kill_switch: KillSwitchCfg = KillSwitchCfg()


class Settings(BaseSettings):
    """Maxfiy kalitlar va muhit sozlamalari — faqat .env / muhit o'zgaruvchilaridan."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    tg_api_id: int | None = None
    tg_api_hash: str | None = None
    tg_session_path: str = "data/hunter.session"
    bot_token: str | None = None
    admin_id: int | None = None
    target_channel: str | None = None
    source_channels_raw: str = Field("", alias="SOURCE_CHANNELS")
    anthropic_api_key: str | None = None
    database_url: str = "sqlite+aiosqlite:///data/hunter.db"
    dry_run: bool = True
    config_path: str = "config.yaml"
    log_level: str = "INFO"

    @property
    def source_channels(self) -> list[str]:
        return [s.strip() for s in self.source_channels_raw.split(",") if s.strip()]

    def require_telegram(self) -> None:
        missing = [
            name
            for name, val in (
                ("TG_API_ID", self.tg_api_id),
                ("TG_API_HASH", self.tg_api_hash),
                ("SOURCE_CHANNELS", self.source_channels or None),
            )
            if not val
        ]
        if missing:
            raise RuntimeError(f".env da to'ldirilmagan: {', '.join(missing)}")


def load_app_config(path: str | Path) -> AppConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(data)


@lru_cache
def get_settings() -> Settings:
    return Settings()
