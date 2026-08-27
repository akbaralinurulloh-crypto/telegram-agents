import os
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, Tuple
from PIL import Image, ImageStat
from pydantic import BaseModel
from app.core.logging import logger


class TechnicalQualityReport(BaseModel):
    score: int               # 0 - 100
    width: int = 0
    height: int = 0
    duration: float = 0.0
    aspect_ratio: str = ""
    is_hd: bool = False
    brightness: float = 0.0  # 0 - 255
    contrast: float = 0.0    # RMS contrast
    has_audio: bool = True
    issues: list[str] = []


class QualityEngine:
    """Media fayllarning texnik sifatini (resolution, contrast, audio, duration) baholovchi engine."""

    @staticmethod
    def _analyze_image_stats(img: Image.Image) -> Tuple[float, float, float]:
        # Kulrangga o'tkazib yorug'lik, kontrast va tiniqlikni (sharpness) hisoblash
        gray = img.convert('L')
        stat = ImageStat.Stat(gray)
        mean_brightness = stat.mean[0]
        rms_contrast = stat.rms[0]
        
        # Edge variance orqali xiralik (blur) darajasini aniqlash
        from PIL import ImageFilter
        edges = gray.filter(ImageFilter.FIND_EDGES)
        edge_stat = ImageStat.Stat(edges)
        sharpness = edge_stat.var[0] if edge_stat.var else 50.0

        return mean_brightness, rms_contrast, sharpness

    @classmethod
    def evaluate_photo(cls, file_path: Path) -> TechnicalQualityReport:
        issues = []
        try:
            with Image.open(file_path) as img:
                w, h = img.size
                brightness, contrast, sharpness = cls._analyze_image_stats(img)

                score = 70
                # Resolution tekshiruvi
                if w >= 1920 or h >= 1920:
                    score += 15
                elif w >= 1080 or h >= 1080:
                    score += 10
                elif w < 600 or h < 600:
                    score -= 25
                    issues.append("Past pikselli tasvir (kichik o'lcham)")

                # Tiniqlik (Blur / Sharpness) tekshiruvi
                if sharpness < 15.0:
                    score -= 20
                    issues.append("Xira (fokussiz / blur) tasvir")
                elif sharpness > 150.0:
                    score += 5

                # Yorug'lik tekshiruvi
                if brightness < 35:
                    score -= 15
                    issues.append("O'ta qorong'u tasvir")
                elif brightness > 225:
                    score -= 15
                    issues.append("O'ta yorug' (perebelyonniy) tasvir")

                # Kontrast tekshiruvi
                if contrast < 25:
                    score -= 15
                    issues.append("Xira (kontrastsiz) tasvir")

                score = max(0, min(100, score))
                aspect = f"{w}:{h}"
                if h > 0 and round(w / h, 2) in [0.56, 0.57]:
                    aspect = "9:16 (Story/Reels)"
                elif h > 0 and round(w / h, 2) in [1.77, 1.78]:
                    aspect = "16:9 (Landscape)"
                elif w == h:
                    aspect = "1:1 (Square)"

                return TechnicalQualityReport(
                    score=score,
                    width=w,
                    height=h,
                    is_hd=(w >= 1080 or h >= 1080),
                    brightness=round(brightness, 1),
                    contrast=round(contrast, 1),
                    aspect_ratio=aspect,
                    issues=issues
                )
        except Exception as e:
            logger.error(f"Rasm sifatini tahlil qilishda xatolik: {e}")
            return TechnicalQualityReport(score=50, issues=[str(e)])

    @classmethod
    def evaluate_video(cls, file_path: Path) -> TechnicalQualityReport:
        issues = []
        # FFprobe mavjud bo'lsa metama'lumotlarni olish
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "stream=width,height,duration,codec_type",
                "-show_entries", "format=duration",
                "-of", "json", str(file_path)
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                streams = data.get("streams", [])
                video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
                has_audio = any(s.get("codec_type") == "audio" for s in streams)

                w = int(video_stream.get("width", 0))
                h = int(video_stream.get("height", 0))
                dur = float(data.get("format", {}).get("duration", video_stream.get("duration", 0.0)))

                score = 70
                if w >= 1080 or h >= 1080:
                    score += 15
                elif w < 480 or h < 480:
                    score -= 20
                    issues.append("Past video piksellari")

                if dur < 3.0:
                    score -= 25
                    issues.append("O'ta qisqa video (< 3 soniya)")
                elif dur > 180.0:
                    score -= 10
                    issues.append("Uzoq video (> 3 daqiqa)")

                score = max(0, min(100, score))
                return TechnicalQualityReport(
                    score=score,
                    width=w,
                    height=h,
                    duration=round(dur, 2),
                    has_audio=has_audio,
                    is_hd=(w >= 1080 or h >= 1080),
                    issues=issues
                )
        except Exception:
            pass

        # Fallback agar ffprobe bo'lmasa
        return TechnicalQualityReport(score=75, issues=["FFprobe yo'q, standart qabul qilindi"])


quality_engine = QualityEngine()
