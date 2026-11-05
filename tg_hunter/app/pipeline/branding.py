"""Logotip / suv belgisi / boshqa kanal reklamasi (OCR ko'ra olmaydigan grafik belgilar) — vizual LLM orqali (Q4)."""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field
from typing import Literal

from PIL import Image

from app.llm.base import LLMClient, LLMError
from app.llm.prompts import load_prompt
from app.pipeline.media_render import Box, apply_patch, area, expand, merge_overlapping

Status = Literal["ok", "reject", "manual_review"]


@dataclass
class BrandingResult:
    status: Status
    image: Image.Image | None = None
    reason: str | None = None
    changed: bool = False
    boxes: list[Box] = field(default_factory=list)


def _jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _parse(data: dict, size: tuple[int, int]) -> tuple[bool | None, list[Box]]:
    flag = data.get("has_branding")
    if not isinstance(flag, bool):
        return None, []
    boxes: list[Box] = []
    for r in data.get("regions") or []:
        b = r.get("box") if isinstance(r, dict) else None
        if isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) for v in b):
            y0, x0, y1, x1 = (max(0, min(1000, v)) for v in b)
            if y1 > y0 and x1 > x0:
                boxes.append((int(x0 / 1000 * size[0]), int(y0 / 1000 * size[1]), int(x1 / 1000 * size[0]), int(y1 / 1000 * size[1])))
    return flag, boxes


async def detect_branding(llm: LLMClient, images: list[Image.Image]) -> tuple[bool | None, list[Box]]:
    data = await llm.generate_json(system=load_prompt("branding"), user="Tasvirni tekshiring.", images=[_jpeg(i) for i in images])
    return _parse(data, images[0].size)


async def remove_branding(llm: LLMClient, img: Image.Image, max_cover_fraction: float = 0.30) -> BrandingResult:
    try:
        flag, boxes = await detect_branding(llm, [img])
    except LLMError:
        return BrandingResult("manual_review", reason="branding_check_llm_error")
    if flag is None:
        return BrandingResult("manual_review", reason="branding_check_ambiguous")
    if flag is False:
        return BrandingResult("ok", img)
    if not boxes:
        return BrandingResult("reject", reason="branding_unlocatable")
    covers = merge_overlapping([expand(b, img.size, 0.15, 0.15) for b in boxes])
    if sum(area(b) for b in covers) > max_cover_fraction * img.width * img.height:
        return BrandingResult("reject", reason="too_much_overlay")
    out = img.convert("RGB")
    for b in covers:
        out = apply_patch(out, b, None)
    try:
        flag2, _ = await detect_branding(llm, [out])
    except LLMError:
        return BrandingResult("manual_review", reason="branding_check_llm_error")
    if flag2 is not False:  # True yoki noaniq — ishonchli yopilmadi
        return BrandingResult("reject", reason="branding_cover_failed")
    return BrandingResult("ok", out, changed=True, boxes=covers)
