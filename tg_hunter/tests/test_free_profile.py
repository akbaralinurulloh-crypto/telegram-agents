import asyncio

import aiohttp
import pytest
import yaml
from pydantic import ValidationError

from app.config import AppConfig, load_app_config
from app.health import HITS, keep_alive_loop, server_port, start_health_server
from app.pipeline.ocr import RapidOCREngine, default_engines


def test_default_engines_are_both_by_default():
    assert [e.name for e in default_engines()] == ["tesseract", "rapidocr"]


def test_tesseract_only_does_not_create_rapidocr():
    engines = default_engines(["tesseract"])
    assert [e.name for e in engines] == ["tesseract"]
    assert not any(isinstance(e, RapidOCREngine) for e in engines)


def test_unknown_ocr_engine_is_rejected_by_config():
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"media": {"ocr_engines": ["magic"]}})


def test_free_profile_extends_base_and_overrides_only_listed_keys():
    base = load_app_config("config.yaml")
    free = load_app_config("config.free.yaml")
    assert free.channel_topic == base.channel_topic and free.scoring.min_score == base.scoring.min_score  # asosdan meros
    assert free.media.ocr_engines == ["tesseract"] and free.media.max_video_seconds == 5
    assert free.media.logo_check == base.media.logo_check  # tegilmagan kalit asosdagicha qoladi
    assert free.watcher.poll_window_hours == 1 and free.watcher.catch_up is False
    assert free.watcher.poll_minutes == base.watcher.poll_minutes


def test_extends_merges_nested_dicts_without_dropping_siblings(tmp_path):
    (tmp_path / "base.yaml").write_text("timezone: Asia/Tashkent\nmedia:\n  max_frames: 50\n  max_video_seconds: 100\n", encoding="utf-8")
    (tmp_path / "over.yaml").write_text("extends: base.yaml\nmedia:\n  max_video_seconds: 7\n", encoding="utf-8")
    cfg = load_app_config(tmp_path / "over.yaml")
    assert cfg.media.max_frames == 50 and cfg.media.max_video_seconds == 7 and cfg.timezone == "Asia/Tashkent"


def test_blueprints_have_no_secret_values_and_free_one_is_free():
    free = yaml.safe_load(open("render.yaml", encoding="utf-8"))["services"][0]
    paid = yaml.safe_load(open("render.paid.yaml", encoding="utf-8"))["services"][0]
    assert free["type"] == "web" and free["plan"] == "free" and free["healthCheckPath"] == "/health" and "disk" not in free
    assert paid["type"] == "worker" and paid["plan"] == "standard" and paid["disk"]["mountPath"] == "/app/data"
    for svc in (free, paid):
        secrets = [e for e in svc["envVars"] if e["key"] in ("TG_API_HASH", "BOT_TOKEN", "GEMINI_API_KEY", "TG_SESSION_STRING")]
        assert len(secrets) == 4 and all(e.get("sync") is False and "value" not in e for e in secrets)


async def test_health_server_answers_and_counts():
    runner = await start_health_server(0, host="127.0.0.1")
    try:
        port = server_port(runner)
        async with aiohttp.ClientSession() as s:
            for path in ("/", "/health"):
                async with s.get(f"http://127.0.0.1:{port}{path}") as r:
                    assert r.status == 200 and (await r.json())["ok"] is True
        assert runner.app[HITS][0] == 2
    finally:
        await runner.cleanup()


async def test_keep_alive_pings_own_health_endpoint():
    runner = await start_health_server(0, host="127.0.0.1")
    try:
        task = asyncio.create_task(keep_alive_loop(f"http://127.0.0.1:{server_port(runner)}", every_seconds=0.05))
        await asyncio.sleep(0.4)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert runner.app[HITS][0] >= 3
    finally:
        await runner.cleanup()


async def test_keep_alive_survives_unreachable_url():
    task = asyncio.create_task(keep_alive_loop("http://127.0.0.1:9", every_seconds=0.05))  # 9-port yopiq
    await asyncio.sleep(0.3)
    assert not task.done()  # xatoda to'xtamaydi
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
