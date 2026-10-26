"""Rasm tozalash (Q4): OCR -> telefon/reklamani topish -> qoplash -> 88 832 77 00 yozish -> qayta OCR bilan tekshirish.

FAIL-CLOSED: qoplashdan keyin ham asl raqam/reklama OCR'da ko'rinsa — REJECT; raqamsimon, lekin
aniqlanmagan qator bo'lsa — qo'lda ko'rib chiqish (manual_review).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from PIL import Image

from app.pipeline.ad_filter import CTA_PHRASES, _LINK_RE, _USERNAME_RE, clean_ads
from app.pipeline.media_render import Box, apply_patch, area, expand, merge_overlapping, ring_color
from app.pipeline.ocr import OCREngine, OCRLine, default_engines, read_all
from app.pipeline.phone_replace import REPLACEMENT, analyze_phones

Status = Literal["ok", "reject", "manual_review"]
_TARGET = re.sub(r"\D", "", REPLACEMENT)
_OCR_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "О": "0", "о": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8", "Z": "2"})
_NUMLIKE_TOKEN = re.compile(r"^[0-9OoОоlI|SBZ()+\-.]+$")


def fix_ocr_digits(text: str) -> str:
    """OCR chalkashtiradigan harflarni (O->0, l->1 ...) FAQAT raqam bor, raqamsimon so'zlarda tuzatadi. Uzunlik saqlanadi."""
    def fix(m: re.Match) -> str:
        tok = m.group()
        return tok.translate(_OCR_DIGIT_FIX) if _NUMLIKE_TOKEN.match(tok) and any(c.isdigit() for c in tok) else tok

    return re.sub(r"\S+", fix, text)


@dataclass
class Flag:
    kind: Literal["phone", "ad", "uncertain"]
    box: Box
    text: str = ""


@dataclass
class MediaResult:
    status: Status
    image: Image.Image | None = None
    reason: str | None = None
    changed: bool = False
    flags: list[Flag] = field(default_factory=list)
    new_number_verified: bool | None = None


def flags_in_line(line: OCRLine) -> list[Flag]:
    text = fix_ocr_digits(line.text)
    flags: list[Flag] = []
    a = analyze_phones(text)
    for s, e in a.phones:
        flags.append(Flag("phone", line.box_for_span(s, e), text[s:e]))
    for s, e, raw in a.uncertain:
        if re.sub(r"\D", "", raw) in _TARGET:  # o'zimiz yozgan 88 832 77 00 ning OCR'da bo'lib o'qilgan qismi
            continue
        flags.append(Flag("uncertain", line.box_for_span(s, e), raw))
    low = line.text.lower()
    for m in list(_LINK_RE.finditer(line.text)) + list(_USERNAME_RE.finditer(line.text)):
        flags.append(Flag("ad", line.box_for_span(m.start(), m.end()), m.group()))
    if any(c.lower() in low for c in CTA_PHRASES):
        flags.append(Flag("ad", line.box, line.text))
    return flags


def _overlap(a: Box, b: Box) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy / max(1, min(area(a), area(b)))


def reconcile_flags(flags: list[Flag]) -> list[Flag]:
    """Dvigatellar bir joyni turlicha o'qiganda: raqam/reklama sifatida tanilgan joydagi 'noaniq' belgi alohida muammo emas."""
    solid = [f for f in flags if f.kind in ("phone", "ad")]
    return [f for f in flags if f.kind != "uncertain" or not any(_overlap(f.box, s.box) > 0.5 for s in solid)]


def scan_image(img: Image.Image, engines: list[OCREngine]) -> tuple[list[Flag], str]:
    """Rasmdagi barcha bayroqlar va umumiy OCR matni."""
    flags: list[Flag] = []
    texts: list[str] = []
    for _, line in read_all(img, engines):
        flags.extend(flags_in_line(line))
        texts.append(line.text)
    return reconcile_flags(flags), "\n".join(texts)


def _number_readable(img: Image.Image, engines: list[OCREngine]) -> bool:
    for _, line in read_all(img, engines):
        if _TARGET in re.sub(r"\D", "", fix_ocr_digits(line.text)):
            return True
    return False


# Qoplash variantlari: (gorizontal pad, vertikal pad, matn rangini teskari qilish)
_VARIANTS = [(0.30, 0.25, False), (0.55, 0.45, False), (0.55, 0.45, True)]


def _apply(img: Image.Image, flags: list[Flag], variant: tuple[float, float, bool]) -> Image.Image:
    px, py, invert = variant
    out = img.convert("RGB")
    phones = merge_overlapping([expand(f.box, img.size, px, py) for f in flags if f.kind == "phone"])
    ads = merge_overlapping([expand(f.box, img.size, px, py) for f in flags if f.kind == "ad"])
    for box in ads:
        out = apply_patch(out, box, None)
    for box in phones:
        out = apply_patch(out, box, REPLACEMENT, invert=invert)
    return out


def clean_image(
    img: Image.Image,
    engines: list[OCREngine] | None = None,
    max_cover_fraction: float = 0.30,
) -> MediaResult:
    engines = engines or default_engines()
    flags, text = scan_image(img, engines)

    verdict = clean_ads(text).reject_reason
    if verdict in ("commercial_ad", "marked_advertisement"):
        return MediaResult("reject", reason=f"image_{verdict}", flags=flags)
    if any(f.kind == "uncertain" for f in flags):
        return MediaResult("manual_review", reason="phone_uncertain_in_image", flags=flags)
    actionable = [f for f in flags if f.kind in ("phone", "ad")]
    if not actionable:
        return MediaResult("ok", img, changed=False, flags=flags)

    covered = sum(area(b) for b in merge_overlapping([expand(f.box, img.size, 0.3, 0.25) for f in actionable]))
    if covered > max_cover_fraction * img.width * img.height:
        return MediaResult("reject", reason="too_much_overlay", flags=flags)

    needs_number = any(f.kind == "phone" for f in actionable)
    last_clean: Image.Image | None = None
    for variant in _VARIANTS:
        out = _apply(img, actionable, variant)
        left, _ = scan_image(out, engines)
        if any(f.kind in ("phone", "ad", "uncertain") for f in left):
            continue  # qoplash yetmadi — kattaroq pad bilan qayta urinamiz
        last_clean = out
        if not needs_number or _number_readable(out, engines):
            return MediaResult("ok", out, changed=True, flags=actionable, new_number_verified=True if needs_number else None)
    if last_clean is not None:
        return MediaResult("manual_review", last_clean, reason="new_number_unverified", changed=True, flags=actionable, new_number_verified=False)
    return MediaResult("reject", reason="cover_failed", flags=actionable)
