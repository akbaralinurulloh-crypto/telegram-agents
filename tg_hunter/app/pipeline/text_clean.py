"""Matnni tozalash: avval reklama, so'ng telefon raqam. Ishonchsiz bo'lsa — fail-closed."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.pipeline.ad_filter import clean_ads
from app.pipeline.phone_replace import replace_phones

Status = Literal["ok", "reject", "manual_review"]


@dataclass
class TextCleanResult:
    text: str
    status: Status = "ok"
    reason: str | None = None
    phones_replaced: int = 0
    ads_removed: list[str] = field(default_factory=list)
    uncertain_numbers: list[str] = field(default_factory=list)


def clean_text(text: str) -> TextCleanResult:
    ad = clean_ads(text)
    if ad.reject_reason:
        return TextCleanResult(text, "reject", ad.reject_reason)
    ph = replace_phones(ad.text)
    base = dict(text=ph.text, phones_replaced=ph.replaced, ads_removed=ad.removed, uncertain_numbers=ph.uncertain)
    if ph.uncertain:
        # Raqamni ishonchli almashtirib bo'lmadi: joylanmaydi, hisobotda "qo'lda ko'rib chiqing".
        return TextCleanResult(status="manual_review", reason="phone_uncertain", **base)
    return TextCleanResult(**base)
