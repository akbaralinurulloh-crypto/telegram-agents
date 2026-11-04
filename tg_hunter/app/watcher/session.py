"""Telethon sessiyasini bitta matn (TG_SESSION_STRING) ko'rinishida ko'chirish.

Nima uchun: Railway/Render kabi "GitHub'ni ulaysiz, o'zi ishga tushadi" xizmatlarida sessiya faylini qo'lda
yuklab bo'lmaydi. Shuning uchun sessiya uzun matn bo'lib muhit o'zgaruvchisiga (TG_SESSION_STRING) qo'yiladi.
Birinchi ishga tushishda undan oddiy sessiya fayli yaratiladi; keyingi ishga tushishlarda fayl ishlatiladi
(shuning uchun u saqlanadigan diskda, ya'ni volume'da turishi kerak).

DIQQAT: bu matn Telegram akkauntingizga TO'LIQ kirish beradi. Uni GitHub'ga, chatga, skrinshotga qo'ymang.
"""
from __future__ import annotations

import os
from pathlib import Path

from telethon.sessions import SQLiteSession, StringSession


def session_file(path: str) -> Path:
    """Telethon `path` oxiriga '.session' qo'shadi (agar yo'q bo'lsa): haqiqiy fayl nomi shu."""
    p = Path(path)
    return p if p.name.endswith(".session") else p.with_name(p.name + ".session")


def ensure_session_file(path: str, session_string: str | None) -> bool:
    """Sessiya fayli yo'q va matn berilgan bo'lsa, fayl yaratadi. Yaratilsa True qaytaradi.

    Fayl bor bo'lsa tegmaydi: unda yangiroq holat (yangilanishlar pozitsiyasi, kanal ma'lumotlari) bo'ladi.
    """
    text = (session_string or "").strip()
    if not text:
        return False
    target = session_file(path)
    if target.exists():
        return False
    try:
        src = StringSession(text)
    except Exception as exc:  # noto'g'ri versiya, uzunlik yoki base64
        raise ValueError(
            "TG_SESSION_STRING yaroqsiz: matnni boshidan oxirigacha, bo'shliq va qator uzilishlarisiz nusxalaganingizni tekshiring"
        ) from exc
    if not src.auth_key:
        raise ValueError("TG_SESSION_STRING ichida kirish kaliti yo'q (login tugallanmagan sessiya)")
    target.parent.mkdir(parents=True, exist_ok=True)
    dst = SQLiteSession(str(target))
    try:
        dst.set_dc(src.dc_id, src.server_address, src.port)  # avval DC, keyin kalit (set_dc kalitni jadvaldan o'qiydi)
        dst.auth_key = src.auth_key
        dst.save()
    finally:
        dst.close()
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass  # Windows / ba'zi fayl tizimlarida mumkin emas
    return True


def export_session_string(path: str) -> str:
    """Mavjud sessiya faylidan TG_SESSION_STRING matnini chiqaradi."""
    target = session_file(path)
    if not target.exists():
        raise FileNotFoundError(f"Sessiya fayli topilmadi: {target}. Avval: python -m scripts.login")
    sess = SQLiteSession(str(target))
    try:
        text = StringSession.save(sess)
    finally:
        sess.close()
    if not text:
        raise ValueError("Sessiya faylida kirish kaliti yo'q (login tugallanmagan). Avval: python -m scripts.login")
    return text
