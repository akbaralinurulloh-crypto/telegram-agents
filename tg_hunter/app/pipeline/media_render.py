"""Qoplash va yangi raqamni chizish yordamchilari."""
from __future__ import annotations

import statistics

from PIL import Image, ImageDraw, ImageFont

Box = tuple[int, int, int, int]


def expand(box: Box, size: tuple[int, int], pad_x: float, pad_y: float) -> Box:
    w, h = box[2] - box[0], box[3] - box[1]
    px, py = max(3, int(h * pad_x)), max(2, int(h * pad_y))
    return (max(0, box[0] - px), max(0, box[1] - py), min(size[0], box[2] + px), min(size[1], box[3] + py))


def area(box: Box) -> int:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def merge_overlapping(boxes: list[Box], gap: int = 4) -> list[Box]:
    """Bir-biriga tegib turgan yoki juda yaqin to'rtburchaklarni birlashtiradi."""
    boxes = [tuple(b) for b in boxes]
    changed = True
    while changed:
        changed = False
        out: list[Box] = []
        for b in boxes:
            for i, o in enumerate(out):
                if b[0] <= o[2] + gap and o[0] <= b[2] + gap and b[1] <= o[3] + gap and o[1] <= b[3] + gap:
                    out[i] = (min(b[0], o[0]), min(b[1], o[1]), max(b[2], o[2]), max(b[3], o[3]))
                    changed = True
                    break
            else:
                out.append(b)
        boxes = out
    return boxes


def ring_color(img: Image.Image, box: Box, width: int = 4) -> tuple[int, int, int]:
    """Qoplanadigan joy atrofidagi piksellarning mediani — fon rangi sifatida."""
    rgb = img.convert("RGB")
    x0, y0, x1, y1 = box
    X0, Y0, X1, Y1 = max(0, x0 - width), max(0, y0 - width), min(rgb.width, x1 + width), min(rgb.height, y1 + width)
    px = rgb.load()
    samples: list[tuple[int, int, int]] = []
    for x in range(X0, X1):
        for y in list(range(Y0, y0)) + list(range(y1, Y1)):
            if 0 <= y < rgb.height:
                samples.append(px[x, y])
    for y in range(y0, y1):
        for x in list(range(X0, x0)) + list(range(x1, X1)):
            if 0 <= x < rgb.width and 0 <= y < rgb.height:
                samples.append(px[x, y])
    if not samples:
        return (0, 0, 0)
    return tuple(int(statistics.median(c[i] for c in samples)) for i in range(3))  # type: ignore[return-value]


def contrast_color(bg: tuple[int, int, int], invert: bool = False) -> tuple[int, int, int]:
    lum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
    dark = lum > 128
    if invert:
        dark = not dark
    return (0, 0, 0) if dark else (255, 255, 255)


def fit_font(text: str, max_w: int, max_h: int) -> ImageFont.FreeTypeFont:
    lo, hi, best = 6, max(8, max_h * 2), 6
    while lo <= hi:
        mid = (lo + hi) // 2
        f = ImageFont.load_default(size=mid)
        l, t, r, b = f.getbbox(text)
        if r - l <= max_w and b - t <= max_h:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return ImageFont.load_default(size=best)


def render_patch(size: tuple[int, int], bg: tuple[int, int, int], text: str | None, invert: bool = False, fill: float = 0.85) -> Image.Image:
    """Fon rangidagi to'rtburchak; `text` berilsa — uning ichiga sig'diriladigan yozuv. Reklama uchun text=None."""
    patch = Image.new("RGB", size, bg)
    if text:
        w, h = size
        f = fit_font(text, int(w * 0.96), int(h * fill))
        l, t, r, b = f.getbbox(text)
        d = ImageDraw.Draw(patch)
        d.text(((w - (r - l)) / 2 - l, (h - (b - t)) / 2 - t), text, font=f, fill=contrast_color(bg, invert))
    return patch


def apply_patch(img: Image.Image, box: Box, text: str | None, bg: tuple[int, int, int] | None = None, invert: bool = False) -> Image.Image:
    out = img.convert("RGB").copy() if img.mode != "RGB" else img.copy()
    bg = bg or ring_color(out, box)
    size = (box[2] - box[0], box[3] - box[1])
    out.paste(render_patch(size, bg, text, invert), (box[0], box[1]))
    return out
