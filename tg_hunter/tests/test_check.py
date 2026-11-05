from app.config import AppConfig, Settings
from scripts.check import offline_checks


def test_offline_check_flags_missing_settings():
    res = offline_checks(Settings(_env_file=None), AppConfig())
    bad = [m for ok, m in res if not ok]
    assert any("TG_API_ID" in m for m in bad) and any("BOT_TOKEN" in m for m in bad) and any("LLM kaliti" in m for m in bad)
    assert any("channel_topic" in m for m in bad)


def test_offline_check_passes_complete_settings(tmp_path):
    s = Settings(_env_file=None, TG_API_ID=1, TG_API_HASH="h", SOURCE_CHANNELS="@a", BOT_TOKEN="t", ADMIN_ID=5, TARGET_CHANNEL="@c", GEMINI_API_KEY="k", TG_SESSION_PATH=str(tmp_path / "x"))
    (tmp_path / "x.session").write_text("")
    cfg = AppConfig(channel_topic="Umra va ziyorat haqida foydali ma'lumotlar, qoidalar va maslahatlar kanal mavzusi.")
    res = dict((m, ok) for ok, m in offline_checks(s, cfg))
    assert all(v for k, v in res.items() if "Telethon session" in k or "TG_API" in k or "BOT_TOKEN" in k or "LLM kaliti" in k or "channel_topic" in k or "DRY_RUN" in k)
