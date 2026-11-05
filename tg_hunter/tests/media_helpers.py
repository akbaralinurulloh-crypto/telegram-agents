from __future__ import annotations

import random
import re

from PIL import Image, ImageDraw, ImageFont

from app.pipeline.media_clean import fix_ocr_digits
from app.pipeline.ocr import default_engines, read_all

TARGET = "888327700"


def make_image(lines, bg=(40, 90, 160), size=(640, 320), noise=0, seed=1) -> Image.Image:
    """lines: [(matn, (x, y), shrift_o'lchami, rang)]"""
    img = Image.new("RGB", size, bg)
    if noise:
        rng = random.Random(seed)
        px = img.load()
        for x in range(size[0]):
            for y in range(size[1]):
                n = rng.randint(-noise, noise)
                r, g, b = px[x, y]
                px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    d = ImageDraw.Draw(img)
    for text, xy, fs, color in lines:
        d.text(xy, text, font=ImageFont.load_default(size=fs), fill=color)
    return img


def ocr_digit_strings(img: Image.Image) -> list[str]:
    """Mustaqil OCR (barcha dvigatel): har qator uchun faqat raqamlar."""
    return [re.sub(r"\D", "", fix_ocr_digits(line.text)) for _, line in read_all(img, default_engines())]


def ocr_text(img: Image.Image) -> str:
    return "\n".join(line.text for _, line in read_all(img, default_engines()))
