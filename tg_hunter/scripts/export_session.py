"""Sessiya matni (TG_SESSION_STRING) va Railway/Render uchun tayyor o'zgaruvchilar blokini chiqaradi.

    python -m scripts.export_session                      # faqat TG_SESSION_STRING qatori
    python -m scripts.export_session --vars               # Render/Railway o'zgaruvchilari uchun to'liq blok (--railway ham ishlaydi)
    python -m scripts.export_session --vars --out data/variables.txt   # faylga (RENDER_UCHUN_SESSIYA.bat ishlatadi)

DIQQAT: natija Telegram akkauntingizga TO'LIQ kirish va API kalitlaringizni o'z ichiga oladi.
Uni GitHub'ga, chatga, skrinshotga qo'ymang.

Nega .env ni xom nusxalamaymiz: Render/Railway qatordagi izohni (`DRY_RUN=true  # ...`) qiymatga qo'shib yuborishi mumkin
va dastur ishga tushmay qoladi. Bu blok qiymatlarni .env dan to'g'ri o'qib, toza qatorlar qilib beradi.
"""
import argparse
from pathlib import Path

from app.config import Settings, get_settings
from app.watcher.session import export_session_string


def railway_block(s: Settings, session_line: str) -> str:
    """Railway Variables uchun toza KEY=VALUE qatorlari. Birinchi ishga tushirish har doim DRY-RUN."""
    pairs = [
        ("TG_API_ID", s.tg_api_id),
        ("TG_API_HASH", s.tg_api_hash),
        ("BOT_TOKEN", s.bot_token),
        ("ADMIN_ID", s.admin_id),
        ("TARGET_CHANNEL", s.target_channel),
        ("SOURCE_CHANNELS", s.source_channels_raw),
        ("GEMINI_API_KEY", s.gemini_api_key),
        ("ANTHROPIC_API_KEY", s.anthropic_api_key),
        ("DRY_RUN", "true"),
    ]
    lines = [f"{k}={v}" for k, v in pairs if v not in (None, "")]
    lines.append(session_line)
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vars", "--railway", dest="railway", action="store_true", help="Render/Railway o'zgaruvchilari uchun to'liq blok (kalitlar + sessiya)")
    ap.add_argument("--out", help="natijani shu faylga yozadi (ekranga chiqarmaydi)")
    args = ap.parse_args()
    s = get_settings()
    try:
        session_line = f"TG_SESSION_STRING={export_session_string(s.tg_session_path)}"
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"XATO: {exc}")
    text = railway_block(s, session_line) if args.railway else session_line
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")  # oxirida qator uzilishi yo'q: nusxalaganda ortiqcha belgi qo'shilmaydi
        print(f"OK: matn {out} fayliga yozildi (MAXFIY!).")
    else:
        print("DIQQAT: quyidagi matn Telegram akkauntingizga to'liq kirish beradi. Faqat Railway/server 'Variables' bo'limiga qo'ying.\n")
        print(text)


if __name__ == "__main__":
    main()
