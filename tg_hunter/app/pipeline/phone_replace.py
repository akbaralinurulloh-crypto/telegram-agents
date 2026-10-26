"""Matndagi telefon raqamlarni 88 832 77 00 ga almashtirish (Q4).

Strategiya: avval raqamlarni normallashtiramiz (keycap emoji, arab/fullwidth raqamlar),
so'ng qat'iy shablonlar bilan topamiz, narx/ID/sana kontekstini tekshiramiz.
Ishonchsiz qolgan raqamsimon qatorlar `uncertain` ro'yxatiga tushadi (fail-closed).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

REPLACEMENT = "88 832 77 00"
_TARGET_DIGITS = "888327700"

# Raqamlar orasidagi "shovqin": 0-2 bo'shliq YOKI bitta belgi/emoji/harf (atrofida bittadan bo'shliq).
_N = r"(?:[  \t]?(?:[^\w\s]|[A-Za-z_])[  \t]?|[  \t]{0,2})"
_D = rf"{_N}\d"
_CODES = "20|33|50|55|61|62|65|66|67|69|70|71|72|73|74|75|76|77|78|79|87|88|90|91|93|94|95|97|98|99"
_LB = r"(?<![\w])(?<!\d[  \-.])"
_RB = r"(?![  \-.]?\d)"

_UZ_FULL = rf"(?P<full>(?:\+[  ]?|00[  ]?)?\(?998\)?(?:{_D}){{9}})"
_INTL = rf"(?P<intl>\+[  ]?\d(?:{_D}){{9,13}})"
_UZ_LOCAL = rf"(?P<local>(?:[80][  \-]?)?\(?(?:{_CODES})\)?(?:{_D}){{7}})"
_RU = rf"(?P<ru>[78](?:{_D}){{10}})"
_PHONE_RE = re.compile(_LB + "(?:" + "|".join((_UZ_FULL, _INTL, _UZ_LOCAL, _RU)) + ")" + _RB)

_UNCERTAIN_RE = re.compile(_LB + rf"\d(?:{_D}){{8,}}" + r"(?!\d)")
_KEYWORD_RE = re.compile(
    r"(?:tel(?:efon)?|aloqa|bog['’ʻ`]?lan|whatsapp|watsap|viber|номер|тел(?:ефон)?|звон|call|📞|☎️?|📱)"
    rf"[^\d\n]{{0,15}}(?P<num>\d(?:{_D}){{6,}})(?!\d)",
    re.IGNORECASE,
)

# Telefon bo'lmagan, lekin raqamlardan iborat tuzilmalar: sana, vaqt, IP, karta.
_NON_PHONE_RE = re.compile(
    r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}:\d{2}(?::\d{2})?\b"
    r"|\b\d{1,3}(?:\.\d{1,3}){3}\b|\b\d{4}(?:[ -]\d{4}){3}\b"
)

_CURRENCY_AFTER = re.compile(
    r"^\s*(?:so['’ʻ`‘]?m|сум|sum|uzs|usd|\$|dollar|доллар|ming|mln|млн|тыс|руб|₽|€|%|ta\b|dona|kg|ml|sm\b)",
    re.IGNORECASE,
)
_ID_BEFORE = re.compile(
    r"(?:narx|цена|price|summa|сумма|\bid|№|#|buyurtma|zakaz|заказ|order|\bkod|code|код|artikul|артикул|"
    r"\binn|stir|pnfl|раздел|raqami|chek)[\s:.\-]*$",
    re.IGNORECASE,
)


@dataclass
class PhoneResult:
    text: str
    replaced: int = 0
    uncertain: list[str] = field(default_factory=list)


@dataclass
class PhoneAnalysis:
    """Asl matndagi [start, end) pozitsiyalar: topilgan raqamlar va ishonchsiz raqamsimon qatorlar."""

    phones: list[tuple[int, int]] = field(default_factory=list)
    uncertain: list[tuple[int, int, str]] = field(default_factory=list)


def _normalize(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Keycap/unicode raqamlarni oddiy raqamga aylantiradi; har belgi uchun asl (start, end) ni saqlaydi."""
    out: list[str] = []
    spans: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "0123456789" and text[i + 1 : i + 3] in ("\ufe0f\u20e3", "\u20e3"):
            j = i + 3 if text[i + 1] == "\ufe0f" else i + 2
            out.append(ch)
            spans.append((i, j))
            i = j
            continue
        if ch.isdecimal() and not ch.isascii():
            out.append(str(unicodedata.decimal(ch)))
        elif ch == "🔟":
            out.append("1")
            spans.append((i, i + 1))
            i += 1
            continue
        else:
            out.append(ch)
        spans.append((i, i + 1))
        i += 1
    return "".join(out), spans


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _is_price_or_id(norm: str, start: int, end: int) -> bool:
    return bool(_CURRENCY_AFTER.match(norm[end : end + 14]) or _ID_BEFORE.search(norm[max(0, start - 20) : start]))


def _looks_like_price_grouping(matched: str) -> bool:
    """905 000 000 kabi ming-guruhli, nol bilan tugaydigan qatorlar narxga o'xshaydi."""
    return bool(re.fullmatch(r"\d{3}([ .]000){2}", matched.strip()))


def analyze_phones(text: str, replacement: str = REPLACEMENT) -> PhoneAnalysis:
    if not text:
        return PhoneAnalysis()
    norm, spans = _normalize(text)
    masked = list(norm)
    already_target = _digits(replacement)
    out = PhoneAnalysis()

    for m in _PHONE_RE.finditer(norm):
        start, end = m.start(), m.end()
        kind = m.lastgroup
        matched = m.group()
        masked[start:end] = " " * (end - start)
        if _digits(matched) in (already_target, _TARGET_DIGITS, "998" + already_target):
            continue
        if kind in ("local", "ru") and (_is_price_or_id(norm, start, end) or _looks_like_price_grouping(matched)):
            continue
        out.phones.append((spans[start][0], spans[end - 1][1]))

    for m in _NON_PHONE_RE.finditer("".join(masked)):
        masked[m.start() : m.end()] = " " * (m.end() - m.start())
    rest = "".join(masked)
    seen: set[tuple[int, int]] = set()
    for m in _UNCERTAIN_RE.finditer(rest):
        if not _is_price_or_id(rest, m.start(), m.end()):
            seen.add((m.start(), m.end()))
    for m in _KEYWORD_RE.finditer(rest):
        if (m.start("num"), m.end("num")) not in seen and not _is_price_or_id(rest, m.start("num"), m.end("num")):
            seen.add((m.start("num"), m.end("num")))
    for s, e in sorted(seen):
        out.uncertain.append((spans[s][0], spans[e - 1][1], norm[s:e]))
    return out


def replace_phones(text: str, replacement: str = REPLACEMENT) -> PhoneResult:
    if not text:
        return PhoneResult(text)
    a = analyze_phones(text, replacement)
    result = text
    for s, e in reversed(a.phones):
        result = result[:s] + replacement + result[e:]
    return PhoneResult(result, len(a.phones), [u[2] for u in a.uncertain])
