"""Rad etish sabablari kodlarini hisobotdagi toifalarga (Uzbek yorliqlar) ajratadi."""

CATEGORIES = {
    "low_score": "past ball",
    "ad": "reklama",
    "phone": "raqamni almashtirib bo'lmadi",
    "duplicate": "dublikat",
    "hadith": "hadis validatori",
    "fact": "fakt validatori",
    "media": "media (qo'llab-quvvatlanmaydi/katta)",
    "error": "xato",
    "other": "boshqa",
}

_EXACT = {
    "low_score": "low_score",
    "duplicate": "duplicate",
    "hadis_validator": "hadith",
    "fact_validator": "fact",
    "caption_failed": "fact",
    "unsupported_media": "media",
    "media_too_large": "media",
    "too_much_overlay": "ad",
    "moving_overlay": "phone",
    "cover_failed": "phone",
    "new_number_unverified": "phone",
    "marked_advertisement": "ad",
    "commercial_ad": "ad",
    "inline_link_or_mention": "ad",
}


def category(reason: str | None) -> str:
    if not reason:
        return "other"
    if reason in _EXACT:
        return _EXACT[reason]
    r = reason.lower()
    if "phone" in r or "number" in r:
        return "phone"
    if any(k in r for k in ("ad", "branding", "overlay")):
        return "ad"
    if "error" in r or "exception" in r or "llm" in r:
        return "error"
    if "video" in r or "media" in r:
        return "media"
    return "other"
