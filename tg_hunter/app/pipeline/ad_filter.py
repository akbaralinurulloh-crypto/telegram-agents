"""Matndagi reklamani tozalash yoki rad etish (Q4, matn qismi).

Xavfsiz tozalash: havola/username faqat gap OXIRIDA yoki BOSHIDA kelsa, yoki butun qator
reklama chaqirig'i bo'lsa olib tashlanadi. Gap o'rtasida bo'lsa — gap buziladi, shuning uchun REJECT.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_LINK_RE = re.compile(
    r"(?:https?://|www\.)\S+"
    r"|\b(?:t\.me|telegram\.me|telegram\.dog|wa\.me|instagram\.com|youtube\.com|youtu\.be|tiktok\.com|"
    r"facebook\.com|fb\.com|bit\.ly|linktr\.ee|ig\.me)/\S*",
    re.IGNORECASE,
)
_USERNAME_RE = re.compile(r"(?<![\w@./])@[A-Za-z][A-Za-z0-9_]{3,31}\b")

CTA_PHRASES = [
    "obuna bo", "obuna bo'l", "obuna bo‘l", "obuna bo’l", "obuna buling", "kanalga qo'shil", "kanalga qo‘shil",
    "kanalimizga", "kanalimiz", "bizning kanal", "a'zo bo'l", "a’zo bo’l", "a‘zo bo‘l", "azo bo'l",
    "guruhimizga", "bizga qo'shil", "bizga qo‘shil", "obuna", "подписыва", "подпишись", "подписаться",
    "присоединя", "наш канал", "наш телеграм", "в нашем канале", "subscribe", "join us", "join our",
    "follow us", "reklama", "реклама", "на правах рекламы",
]
COMMERCIAL_KEYWORDS = [
    "sotiladi", "sotuvda", "sotib oling", "sotib olish", "chegirma", "aksiya", "skidka", "buyurtma bering",
    "buyurtma uchun", "yetkazib berish", "dostavka", "arzon narxda", "narxlar", "prays",
    "продается", "продаётся", "продаю", "скидка", "акция", "заказать", "заказ по", "доставка", "купить", "прайс",
]
_AD_MARKERS = re.compile(r"#\s*(?:reklama|реклама|ad|ads)\b|\bреклама\b\s*[:.]|\breklama huquqida\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[^\W_]{2,}", re.UNICODE)


@dataclass
class AdResult:
    text: str
    removed: list[str] = field(default_factory=list)
    reject_reason: str | None = None

    @property
    def changed(self) -> bool:
        return bool(self.removed)


def _words(s: str) -> int:
    return len(_WORD_RE.findall(s))


def _tidy(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_ads(
    text: str,
    cta_phrases: list[str] | None = None,
    commercial_keywords: list[str] | None = None,
) -> AdResult:
    if not text:
        return AdResult(text)
    ctas = [c.lower() for c in (cta_phrases or CTA_PHRASES)]
    commercial = [c.lower() for c in (commercial_keywords or COMMERCIAL_KEYWORDS)]
    low = text.lower()

    if _AD_MARKERS.search(text):
        return AdResult(text, reject_reason="marked_advertisement")
    if len({k for k in commercial if k in low}) >= 2:
        return AdResult(text, reject_reason="commercial_ad")

    removed: list[str] = []
    kept: list[str] = []
    for line in text.split("\n"):
        tokens = [m for m in list(_LINK_RE.finditer(line)) + list(_USERNAME_RE.finditer(line))]
        is_cta = any(c in line.lower() for c in ctas)
        if is_cta:
            removed.append(line.strip())
            continue
        if not tokens:
            kept.append(line)
            continue
        tokens.sort(key=lambda m: m.start())
        # Gap o'rtasidagi token: oldida ham, ortida ham so'z bor -> xavfsiz tozalab bo'lmaydi.
        for m in tokens:
            before = _words(line[: m.start()])
            after = _words(line[m.end() :])
            others_after = _words(_USERNAME_RE.sub("", _LINK_RE.sub("", line[m.end() :])))
            if before >= 1 and others_after >= 1 and after >= 1:
                return AdResult(text, reject_reason="inline_link_or_mention")
        stripped = _USERNAME_RE.sub("", _LINK_RE.sub("", line))
        removed.extend(m.group() for m in tokens)
        if _words(stripped) <= 2:  # "Batafsil: t.me/x" kabi yorliq qoldig'i
            continue
        kept.append(re.sub(r"[ \t]{2,}", " ", stripped).rstrip(" :-–—→>|"))
    out = _tidy("\n".join(kept))
    out = re.sub(r"^[\s:\-–—→>|]+", "", out)
    return AdResult(out, removed)
