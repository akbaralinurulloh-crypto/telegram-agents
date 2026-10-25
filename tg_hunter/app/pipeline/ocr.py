"""OCR qatlami: bir nechta dvigatel (Tesseract uz/ru/en + RapidOCR) natijalari birlashtiriladi.

Ikki dvigatel — xavfsizlik uchun: bittasi raqam yoki reklamani o'qiy olmasa, ikkinchisi topishi mumkin.
Dvigatellar `OCREngine` protokoliga mos bo'lsa, EasyOCR/PaddleOCR ham shu yerga ulanadi.
"""
from __future__ import annotations

import io
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Protocol

from PIL import Image

Box = tuple[int, int, int, int]  # x0, y0, x1, y1


@dataclass
class OCRWord:
    text: str
    box: Box
    conf: float = 0.0


@dataclass
class OCRLine:
    text: str  # so'zlar bitta bo'shliq bilan birlashtirilgan
    box: Box
    words: list[OCRWord] = field(default_factory=list)
    # words[i] matn ichida [offsets[i], offsets[i] + len(words[i].text)) oralig'ida turadi
    offsets: list[int] = field(default_factory=list)

    @classmethod
    def from_words(cls, words: list[OCRWord]) -> "OCRLine":
        offsets, pos = [], 0
        for w in words:
            offsets.append(pos)
            pos += len(w.text) + 1
        return cls(
            " ".join(w.text for w in words),
            (min(w.box[0] for w in words), min(w.box[1] for w in words), max(w.box[2] for w in words), max(w.box[3] for w in words)),
            words,
            offsets,
        )

    def box_for_span(self, start: int, end: int) -> Box:
        """Matn ichidagi [start, end) belgilar egallagan to'rtburchak (so'zlar chegarasida)."""
        hit = [w for w, o in zip(self.words, self.offsets) if o < end and o + len(w.text) > start]
        if not hit:
            return self.box
        return (min(w.box[0] for w in hit), min(w.box[1] for w in hit), max(w.box[2] for w in hit), max(w.box[3] for w in hit))


class OCREngine(Protocol):
    name: str

    def read(self, img: Image.Image) -> list[OCRLine]: ...


class TesseractEngine:
    name = "tesseract"

    def __init__(self, langs: str = "eng+rus+uzb", psm: int = 11, min_conf: float = 20):
        self.langs, self.psm, self.min_conf = langs, psm, min_conf

    def read(self, img: Image.Image) -> list[OCRLine]:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        proc = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", self.langs, "--psm", str(self.psm), "tsv"],
            input=buf.getvalue(),
            capture_output=True,
            timeout=120,
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},  # parallel kadrlarda protsessorni bo'g'masligi uchun
        )
        if proc.returncode != 0:
            raise RuntimeError(f"tesseract xatosi: {proc.stderr.decode(errors='replace')[:200]}")
        groups: dict[tuple[str, str, str], list[OCRWord]] = {}
        for row in proc.stdout.decode("utf-8", "replace").splitlines()[1:]:
            c = row.split("\t")
            if len(c) < 12 or not c[11].strip():
                continue
            conf = float(c[10])
            if conf < self.min_conf:
                continue
            x, y, w, h = (int(v) for v in c[6:10])
            groups.setdefault((c[2], c[3], c[4]), []).append(OCRWord(c[11].strip(), (x, y, x + w, y + h), conf))
        return [OCRLine.from_words(ws) for ws in groups.values()]


class RapidOCREngine:
    name = "rapidocr"
    _engine = None

    def read(self, img: Image.Image) -> list[OCRLine]:
        import numpy as np

        if RapidOCREngine._engine is None:
            from rapidocr_onnxruntime import RapidOCR

            RapidOCREngine._engine = RapidOCR()
        result, _ = RapidOCREngine._engine(np.array(img.convert("RGB"))[:, :, ::-1])
        lines: list[OCRLine] = []
        for poly, text, conf in result or []:
            xs, ys = [p[0] for p in poly], [p[1] for p in poly]
            x0, y0, x1, y1 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
            parts = [p for p in re.split(r"\s+", text.strip()) if p]
            if not parts:
                continue
            total = sum(len(p) for p in parts) + len(parts) - 1
            words, cur = [], 0
            for p in parts:  # so'z o'rnini belgi soniga proporsional taxmin qilamiz
                wx0 = x0 + (x1 - x0) * cur / total
                wx1 = x0 + (x1 - x0) * (cur + len(p)) / total
                words.append(OCRWord(p, (int(wx0), y0, int(wx1) + 1, y1), float(conf)))
                cur += len(p) + 1
            lines.append(OCRLine.from_words(words))
        return lines


def default_engines() -> list[OCREngine]:
    return [TesseractEngine(), RapidOCREngine()]


def _scaled(line: OCRLine, f: float) -> OCRLine:
    def sb(b: Box) -> Box:
        return (int(b[0] / f), int(b[1] / f), int(b[2] / f), int(b[3] / f))

    return OCRLine(line.text, sb(line.box), [OCRWord(w.text, sb(w.box), w.conf) for w in line.words], line.offsets)


def read_all(img: Image.Image, engines: list[OCREngine], upscale_small: bool = True) -> list[tuple[str, OCRLine]]:
    """Barcha dvigatellar (va kichik rasmlar uchun 2x kattalashtirilgan nusxa) natijalarini (dvigatel, qator) ko'rinishida qaytaradi."""
    variants = [(img, 1.0)]
    if upscale_small and max(img.size) < 1000:
        variants.append((img.resize((img.width * 2, img.height * 2), Image.LANCZOS), 2.0))
    out: list[tuple[str, OCRLine]] = []
    for im, f in variants:
        for eng in engines:
            for line in eng.read(im):
                out.append((eng.name, _scaled(line, f) if f != 1.0 else line))
    return out
