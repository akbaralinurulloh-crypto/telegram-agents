"""Video tozalash (Q4): kadrlarni tanlab OCR -> raqam/reklama joylari va vaqt oralig'ini aniqlash ->
ffmpeg overlay bilan qoplash va 88 832 77 00 yozish -> boshqa kadrlar to'plamida qayta OCR bilan tekshirish.

FAIL-CLOSED: harakatlanayotgan yozuv, qoplash yetmagan holat, juda uzun/katta video — post joylanmaydi.
Cheklov: ovozdagi (audio) telefon raqamlar bu modulda tekshirilmaydi.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from PIL import Image

from app.pipeline.ad_filter import clean_ads
from app.pipeline.media_clean import Flag, _number_readable, flags_in_line, reconcile_flags
from app.pipeline.media_render import Box, area, expand, merge_overlapping, render_patch, ring_color
from app.pipeline.ocr import OCREngine, default_engines, read_all
from app.pipeline.phone_replace import REPLACEMENT

Status = Literal["ok", "reject", "manual_review"]


@dataclass
class VideoInfo:
    width: int
    height: int
    duration: float
    has_audio: bool


@dataclass
class Region:
    kind: str  # "phone" | "ad"
    box: Box
    t0: float
    t1: float
    bg: tuple[int, int, int] = (0, 0, 0)


@dataclass
class VideoResult:
    status: Status
    path: Path | None = None
    reason: str | None = None
    changed: bool = False
    regions: list[Region] = field(default_factory=list)
    new_number_verified: bool | None = None


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def probe(path: Path) -> VideoInfo:
    p = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)])
    if p.returncode != 0:
        raise ValueError(f"ffprobe o'qiy olmadi: {p.stderr.decode(errors='replace')[:200]}")
    data = json.loads(p.stdout)
    v = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    if v is None:
        raise ValueError("videoda video oqim yo'q")
    dur = float(data.get("format", {}).get("duration") or v.get("duration") or 0)
    return VideoInfo(int(v["width"]), int(v["height"]), dur, any(s.get("codec_type") == "audio" for s in data["streams"]))


def sample_frames(path: Path, step: float, offset: float, outdir: Path) -> list[tuple[float, Image.Image]]:
    """Har `step` soniyada bitta kadr: t = offset + k*step."""
    pattern = str(outdir / "f_%05d.png")
    cmd = ["ffmpeg", "-v", "error", "-y"] + (["-ss", f"{offset:.3f}"] if offset > 0 else []) + ["-i", str(path), "-vf", f"fps=1/{step}", "-vsync", "vfr", pattern]
    p = _run(cmd)
    if p.returncode != 0:
        raise ValueError(f"ffmpeg kadr ajratolmadi: {p.stderr.decode(errors='replace')[:200]}")
    files = sorted(outdir.glob("f_*.png"))
    frames = []
    for i, f in enumerate(files):
        with Image.open(f) as im:
            frames.append((offset + i * step, im.convert("RGB")))
        f.unlink()
    return frames


def _scan_frames(frames, engines, workers: int = 4):
    def one(item):
        t, img = item
        flags, texts = [], []
        for _, line in read_all(img, engines, upscale_small=False):
            flags.extend(flags_in_line(line))
            texts.append(line.text)
        return t, img, reconcile_flags(flags), "\n".join(texts)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, frames))


def _center(b: Box) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def _same_place(a: Box, b: Box) -> bool:
    h = max(a[3] - a[1], b[3] - b[1], 8)
    (ax, ay), (bx, by) = _center(a), _center(b)
    return abs(ax - bx) <= 0.6 * h + 6 and abs(ay - by) <= 0.6 * h + 6


def _group(dets: list[tuple[float, Flag, Image.Image]], step: float, size: tuple[int, int]):
    """Aniqlanmalarni joyi bo'yicha guruhlaydi. Qaytaradi: (regions, moving: bool)."""
    groups: list[dict] = []
    for t, f, img in sorted(dets, key=lambda d: d[0]):
        for g in groups:
            if g["kind"] == f.kind and _same_place(g["last"], f.box):
                g["boxes"].append(f.box)
                g["last"], g["t1"] = f.box, t
                break
        else:
            groups.append({"kind": f.kind, "boxes": [f.box], "last": f.box, "t0": t, "t1": t, "img": img})

    moving = False
    for g in groups:  # bitta guruh ichida sezilarli siljish
        c0, c1 = _center(g["boxes"][0]), _center(g["boxes"][-1])
        h = max(g["boxes"][0][3] - g["boxes"][0][1], 8)
        if abs(c0[0] - c1[0]) > 1.0 * h or abs(c0[1] - c1[1]) > 1.0 * h:
            moving = True
    by_kind: dict[str, list[dict]] = {}
    for g in groups:
        by_kind.setdefault(g["kind"], []).append(g)
    for gs in by_kind.values():  # ketma-ket, lekin boshqa joyda paydo bo'ladigan guruhlar = sakrab yurayotgan yozuv
        gs.sort(key=lambda g: g["t0"])
        for a, b in zip(gs, gs[1:]):
            if b["t0"] - a["t1"] <= 2.01 * step:
                moving = True

    regions = []
    for g in groups:
        u = (min(b[0] for b in g["boxes"]), min(b[1] for b in g["boxes"]), max(b[2] for b in g["boxes"]), max(b[3] for b in g["boxes"]))
        box = expand(u, size, 0.35, 0.3)
        regions.append(Region(g["kind"], box, max(0.0, g["t0"] - step), g["t1"] + step, ring_color(g["img"], box)))
    return regions, moving


def _render(path: Path, out: Path, regions: list[Region], info: VideoInfo, tmpdir: Path) -> None:
    inputs, chains, last = ["-i", str(path)], [], "[0:v]"
    for i, r in enumerate(regions, start=1):
        png = tmpdir / f"patch_{i}.png"
        render_patch((r.box[2] - r.box[0], r.box[3] - r.box[1]), r.bg, REPLACEMENT if r.kind == "phone" else None).save(png)
        inputs += ["-i", str(png)]
        nxt = f"[v{i}]"
        chains.append(f"{last}[{i}:v]overlay={r.box[0]}:{r.box[1]}:enable='between(t,{r.t0:.3f},{r.t1:.3f})'{nxt}")
        last = nxt
    base = ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(chains), "-map", last, "-map", "0:a?"]
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    p = _run(base + enc + ["-c:a", "copy", str(out)])
    if p.returncode != 0:  # audio kodeki mp4'ga to'g'ridan-to'g'ri sig'masa
        p = _run(base + enc + ["-c:a", "aac", "-b:a", "128k", str(out)])
    if p.returncode != 0:
        raise ValueError(f"ffmpeg overlay xatosi: {p.stderr.decode(errors='replace')[:300]}")


def clean_video(
    path: Path,
    out_path: Path,
    engines: list[OCREngine] | None = None,
    *,
    sample_interval: float = 0.5,
    max_frames: int = 120,
    max_seconds: float = 300,
    max_mb: float = 100,
    max_cover_fraction: float = 0.30,
    workers: int = 4,
) -> VideoResult:
    engines = engines or default_engines()
    path, out_path = Path(path), Path(out_path)
    if path.stat().st_size > max_mb * 1024 * 1024:
        return VideoResult("reject", reason="video_too_large")
    info = probe(path)
    if info.duration <= 0 or info.duration > max_seconds:
        return VideoResult("manual_review", reason="video_duration_unsupported")
    step = max(sample_interval, info.duration / max_frames)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        scanned = _scan_frames(sample_frames(path, step, 0.0, tmp), engines, workers)
        verdict = clean_ads("\n".join(s[3] for s in scanned)).reject_reason
        if verdict in ("commercial_ad", "marked_advertisement"):
            return VideoResult("reject", reason=f"video_{verdict}")
        if any(f.kind == "uncertain" for _, _, fl, _ in scanned for f in fl):
            return VideoResult("manual_review", reason="phone_uncertain_in_video")
        dets = [(t, f, img) for t, img, fl, _ in scanned for f in fl if f.kind in ("phone", "ad")]
        if not dets:
            return VideoResult("ok", path, changed=False)

        regions, moving = _group(dets, step, (info.width, info.height))
        if moving:
            return VideoResult("reject", reason="moving_overlay", regions=regions)
        if sum(area(b) for b in merge_overlapping([r.box for r in regions])) > max_cover_fraction * info.width * info.height:
            return VideoResult("reject", reason="too_much_overlay", regions=regions)

        _render(path, out_path, regions, info, tmp)

        # Tekshiruv: boshqa vaqt nuqtalarida (yarim qadam siljigan, zichroq) kadrma-kadr OCR.
        vstep = max(step / 2, 0.2)
        checked = _scan_frames(sample_frames(out_path, vstep, vstep / 2, tmp), engines, workers)
        if any(f.kind in ("phone", "ad", "uncertain") for _, _, fl, _ in checked for f in fl):
            out_path.unlink(missing_ok=True)
            return VideoResult("reject", reason="cover_failed", regions=regions)

        needs_number = any(r.kind == "phone" for r in regions)
        verified = None
        if needs_number:
            inside = [img for t, img, _, _ in checked if any(r.kind == "phone" and r.t0 + vstep <= t <= r.t1 - vstep for r in regions)]
            verified = any(_number_readable(img, engines) for img in inside)
            if not verified:
                return VideoResult("manual_review", out_path, reason="new_number_unverified", changed=True, regions=regions, new_number_verified=False)
        return VideoResult("ok", out_path, changed=True, regions=regions, new_number_verified=verified)
