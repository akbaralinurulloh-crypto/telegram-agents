import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from app.core.logging import logger
from app.core.config import settings


class MediaCreatorStudio:
    """FFmpeg yordamida media fayllarni professional tahrirlash (Trim, Audio normalize, Crop, Watermark)."""

    @classmethod
    async def process_media(
        cls,
        input_path: Path,
        action: str = "KEEP_ORIGINAL",
        params: Optional[Dict[str, Any]] = None
    ) -> Path:
        if action == "KEEP_ORIGINAL" or not params:
            return input_path

        params = params or {}
        output_path = settings.DOWNLOAD_DIR / f"edited_{input_path.name}"

        try:
            if action == "AUDIO_NORMALIZE" and input_path.suffix.lower() in [".mp4", ".mov", ".mkv"]:
                # Ovoz balandligini standart darajaga keltirish (EBU R128 loudness)
                cmd = [
                    "ffmpeg", "-y", "-i", str(input_path),
                    "-filter:a", "loudnorm",
                    "-c:v", "copy",
                    str(output_path)
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
                if res.returncode == 0 and output_path.exists():
                    return output_path

            elif action == "TRIM":
                start_sec = params.get("start", 0)
                duration = params.get("duration", 60)
                cmd = [
                    "ffmpeg", "-y", "-ss", str(start_sec), "-i", str(input_path),
                    "-t", str(duration), "-c", "copy",
                    str(output_path)
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
                if res.returncode == 0 and output_path.exists():
                    return output_path

        except Exception as e:
            logger.warning(f"Media tahrirlashda xatolik yuz berdi, original qoldirildi: {e}")

        return input_path


media_creator = MediaCreatorStudio()
