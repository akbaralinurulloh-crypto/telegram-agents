import pytest
from pydantic import ValidationError

from app.config import AppConfig, ScoringWeights, Settings, load_app_config


def test_shipped_config_is_valid():
    cfg = load_app_config("config.yaml")
    assert cfg.timezone == "Asia/Tashkent"
    assert cfg.report_times == ["08:00", "13:00", "20:00"]
    assert cfg.scoring.min_score == 7.0
    assert "hadis" in cfg.banned_caption_keywords and "хадис" in cfg.banned_caption_keywords


def test_weights_must_sum_to_one():
    with pytest.raises(ValidationError):
        ScoringWeights(topic_fit=0.5, quality=0.5, audience_interest=0.5, media_quality=0.5)


def test_caption_limit_cannot_exceed_telegram_cap():
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"caption": {"max_length": 2000}})


def test_source_channels_parsing():
    s = Settings(_env_file=None, SOURCE_CHANNELS=" @a, -1001234 ,,@b ")
    assert s.source_channels == ["@a", "-1001234", "@b"]


def test_dry_run_defaults_on():
    assert Settings(_env_file=None).dry_run is True


def test_require_telegram_lists_missing():
    with pytest.raises(RuntimeError, match="TG_API_ID.*TG_API_HASH.*SOURCE_CHANNELS"):
        Settings(_env_file=None).require_telegram()
