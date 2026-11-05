"""Izoh validatorlari (Q1, Q2, Q3). Muammo kodlari ro'yxatini qaytaradi; bo'sh ro'yxat = o'tdi."""
from __future__ import annotations

import re

from app.pipeline.phone_replace import replace_phones

HADITH_KEYWORD = "hadith_keyword"
UNSUPPORTED_NUMBER = "unsupported_number"

_APOS = str.maketrans({"ʻ": "'", "ʼ": "'", "’": "'", "‘": "'", "`": "'", "´": "'"})
_BUILTIN_RELIGIOUS = re.compile(r"ﷺ|ﷻ|\bs\.\s?a\.\s?[vw]\b|\balayhis\w*|\bʿalayhi\b|\b[rs]\.\s?a\b", re.IGNORECASE)
_EXTRA = re.compile(r"#\w|(?<!\w)@\w|https?://|www\.|\bt\.me/|\bobuna\b|подпи[сш]", re.IGNORECASE)
_NUM = re.compile(r"\d+(?:[ .,]\d{3})*(?:[.,]\d+)?")
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def _norm(s: str) -> str:
    return s.translate(_APOS).lower()


def _num_key(raw: str) -> str:
    return re.sub(r"\D", "", raw)


def _numbers(text: str) -> set[str]:
    return {_num_key(m.group()) for m in _NUM.finditer(text)}


def _sentences(text: str) -> int:
    return len([s for s in _SENT_SPLIT.split(text.strip()) if s.strip()])


def caption_problems(
    caption: str,
    source_text: str,
    *,
    banned_keywords: list[str],
    max_length: int = 1024,
    max_sentences: int = 2,
) -> list[str]:
    problems: list[str] = []
    if not caption or not caption.strip():
        return ["empty"]
    cap = caption.strip()
    if len(cap) > max_length:
        problems.append("too_long")
    if _sentences(cap) > max_sentences:
        problems.append("too_many_sentences")

    low = _norm(cap)
    if _BUILTIN_RELIGIOUS.search(cap) or any(_norm(k) in low for k in banned_keywords if k.strip()):
        problems.append(HADITH_KEYWORD)

    ph = replace_phones(cap)
    if _EXTRA.search(cap) or ph.replaced or ph.uncertain:
        problems.append("extra_content")

    letters = [c for c in cap if c.isalpha()]
    if letters and sum("Ѐ" <= c <= "ӿ" for c in letters) / len(letters) > 0.2:
        problems.append("not_uzbek_latin")

    # Q1: raqamlar faqat manba matnida bor bo'lsa ruxsat; matnsiz postda raqam umuman taqiqlanadi.
    src_nums = _numbers(source_text)
    if any(n not in src_nums for n in _numbers(cap)):
        problems.append(UNSUPPORTED_NUMBER)
    return problems


def verdict_problems(verdict: dict) -> list[str]:
    """LLM validator javobi qat'iy: faqat aniq `True/False` qiymatlar qabul qilinadi, qolgan hammasi — rad."""
    problems: list[str] = []
    if verdict.get("supported") is not True:
        problems.append("unsupported_claim")
    if verdict.get("religious_quote") is not False:
        problems.append(HADITH_KEYWORD)
    if verdict.get("uzbek_latin") is not True:
        problems.append("not_uzbek_latin")
    if verdict.get("extra_content") is not False:
        problems.append("extra_content")
    return problems
