from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 480, 270, 10


def make_video(path: Path, secs: float, frame_fn, with_audio: bool = False) -> Path:
    """frame_fn(i, t) -> PIL.Image (W x H). H.264 mp4 yozadi."""
    n = int(secs * FPS)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "18"] + (["-c:a", "aac", "-shortest"] if with_audio else []) + [str(path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        p.stdin.write(frame_fn(i, i / FPS).convert("RGB").tobytes())
    p.stdin.close()
    assert p.wait() == 0
    return path


def background(t: float) -> Image.Image:
    """Vaqt o'tishi bilan sekin o'zgaradigan fon."""
    c = (int(40 + 20 * t), int(90 + 10 * t), int(160 - 15 * t))
    return Image.new("RGB", (W, H), c)


def with_text(img: Image.Image, text: str, xy, size=30, fill=(255, 255, 255)) -> Image.Image:
    ImageDraw.Draw(img).text(xy, text, font=ImageFont.load_default(size=size), fill=fill)
    return img
