"""Ishga tushirishdan oldingi tekshiruv.

    python -m scripts.check            # oflayn: .env, dasturlar, session fayli
    python -m scripts.check --online   # + Telegram bot, kanallar, admin, LLM (haqiqiy so'rovlar)
"""
import argparse
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

from app.config import AppConfig, Settings, get_settings, load_app_config


def offline_checks(s: Settings, cfg: AppConfig) -> list[tuple[bool, str]]:
    r: list[tuple[bool, str]] = []

    def add(ok: bool, msg: str) -> None:
        r.append((ok, msg))

    add(bool(s.tg_api_id and s.tg_api_hash), "TG_API_ID va TG_API_HASH to'ldirilgan")
    add(bool(s.source_channels), f"Manba kanallar: {', '.join(s.source_channels) or 'YO`Q'}")
    add(bool(s.bot_token), "BOT_TOKEN to'ldirilgan")
    add(bool(s.admin_id), "ADMIN_ID to'ldirilgan")
    add(bool(s.target_channel), f"TARGET_CHANNEL: {s.target_channel or 'YO`Q'}")
    key = s.gemini_api_key if cfg.llm.provider == "gemini" else s.anthropic_api_key
    add(bool(key), f"LLM kaliti ({cfg.llm.provider}) to'ldirilgan")
    add("TODO" not in cfg.channel_topic and len(cfg.channel_topic.strip()) > 30, "config.yaml: channel_topic to'ldirilgan")
    add(s.dry_run, "DRY_RUN=true (birinchi ishga tushirish uchun xavfsiz)")
    for tool in ("ffmpeg", "ffprobe", "tesseract"):
        add(shutil.which(tool) is not None, f"`{tool}` o'rnatilgan")
    if shutil.which("tesseract"):
        langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
        for lang in ("eng", "rus", "uzb"):
            add(lang in langs.split(), f"tesseract tili: {lang}")
    sess = Path(s.tg_session_path)
    add(sess.with_suffix(sess.suffix or ".session").exists() or Path(str(sess) + ".session").exists() or sess.exists(), f"Telethon session fayli ({s.tg_session_path}) — `python -m scripts.login`")
    return r


async def online_checks(s: Settings, cfg: AppConfig) -> list[tuple[bool, str]]:
    from aiogram import Bot

    from app.llm.factory import build_llm
    from app.watcher.listener import Watcher, build_client

    r: list[tuple[bool, str]] = []
    bot = Bot(s.bot_token)
    try:
        me = await bot.get_me()
        r.append((True, f"Bot: @{me.username}"))
        try:
            member = await bot.get_chat_member(s.target_channel, me.id)
            ok = member.status in ("administrator", "creator") and getattr(member, "can_post_messages", True)
            r.append((bool(ok), f"Bot {s.target_channel} da admin va yoza oladi (holat: {member.status})"))
        except Exception as exc:
            r.append((False, f"Bot kanalni ko'ra olmadi: {exc}"))
        try:
            await bot.send_message(s.admin_id, "✅ TG Hunter: tekshiruv xabari")
            r.append((True, "Bot adminga yoza oladi"))
        except Exception as exc:
            r.append((False, f"Bot adminga yoza olmadi (botga /start yozing): {exc}"))
    except Exception as exc:
        r.append((False, f"Bot tokeni yaroqsiz: {exc}"))
    finally:
        await bot.session.close()

    client = build_client(s, cfg)
    await client.connect()
    try:
        r.append((await client.is_user_authorized(), "Telethon akkaunti avtorizatsiyadan o'tgan"))
        w = Watcher(client, None, s.source_channels)
        try:
            await w.resolve_sources()
            r.append((True, "Manba kanallar topildi: " + ", ".join(w.titles.values())))
        except Exception as exc:
            r.append((False, str(exc)))
    finally:
        await client.disconnect()

    try:
        llm = build_llm(s, cfg)
        out = await llm.generate_json(system="# ROLE: PING\nFaqat JSON qaytaring.", user='{"ok": true} ni qaytaring')
        r.append(("ok" in out, f"LLM ({cfg.llm.provider}) javob berdi"))
    except Exception as exc:
        r.append((False, f"LLM ishlamadi: {str(exc)[:160]}"))
    return r


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--online", action="store_true")
    a = p.parse_args()
    s = get_settings()
    cfg = load_app_config(s.config_path)
    results = offline_checks(s, cfg)
    if a.online:
        results += asyncio.run(online_checks(s, cfg))
    for ok, msg in results:
        print(("✅ " if ok else "❌ ") + msg)
    bad = sum(not ok for ok, _ in results)
    print(f"\n{'Hammasi tayyor' if not bad else f'{bad} ta muammo bor'}.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
