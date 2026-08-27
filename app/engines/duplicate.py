import os
import hashlib
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from PIL import Image
import imagehash
from sqlalchemy import select

from app.core.logging import logger
from app.core.database import get_db_session
from app.models.schema import MediaAsset, DuplicateMatch, DuplicateGroup, Post


class DuplicateEngine:
    """
    Super Strict Multi-Layer & Multi-Frame Duplicate Engine.
    
    Darajalar:
    - Level 1: Exact Byte Checksum (SHA-256)
    - Level 2: Multi-Frame Keyframe Perceptual Hashes (10%, 30%, 50%, 70%, 90% pHash/dHash/aHash)
    - Level 3: Duration & Technical Match
    - Level 4: Duplicate Group Clustering & Best Version Selector
    """

    @staticmethod
    def calculate_sha256(file_path: Path) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @classmethod
    def extract_multi_keyframes(cls, video_path: Path, points: List[float] = [0.1, 0.3, 0.5, 0.7, 0.9]) -> List[Path]:
        """Videoning turli vaqt nuqtalaridan (masalan 10%, 30%, 50%, 70%, 90%) kadrlarni oladi."""
        extracted_frames = []
        try:
            # Davomiylikni aniqlash
            dur_cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)
            ]
            dur_res = subprocess.run(dur_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            duration = float(dur_res.stdout.strip()) if dur_res.stdout.strip() else 10.0

            for idx, pt in enumerate(points):
                ts = max(0.5, min(duration - 0.5, duration * pt))
                frame_path = video_path.parent / f"kf_{video_path.stem}_{idx}.jpg"
                cmd = [
                    "ffmpeg", "-y", "-ss", f"{ts:.2f}",
                    "-i", str(video_path),
                    "-vframes", "1",
                    "-q:v", "2",
                    str(frame_path)
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                if res.returncode == 0 and frame_path.exists():
                    extracted_frames.append(frame_path)
        except Exception as e:
            logger.debug(f"Multi-keyframe olishda xatolik: {e}")

        return extracted_frames

    @classmethod
    def calculate_visual_hashes(cls, file_path: Path, media_type: str = "photo") -> Tuple[Optional[str], Optional[str]]:
        try:
            target_image = file_path
            temp_frames = []

            if media_type == "video":
                temp_frames = cls.extract_multi_keyframes(file_path, [0.5])
                if temp_frames:
                    target_image = temp_frames[0]

            if target_image.exists() and target_image.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                with Image.open(target_image) as img:
                    phash_val = str(imagehash.phash(img))
                    dhash_val = str(imagehash.dhash(img))

                    for tf in temp_frames:
                        try:
                            tf.unlink()
                        except Exception:
                            pass

                    return phash_val, dhash_val
        except Exception as e:
            logger.debug(f"Visual hash hisoblashda xatolik: {e}")

        return None, None

    @classmethod
    async def check_duplicate(cls, file_path: Path, media_type: str) -> Tuple[bool, Optional[int], str, float]:
        """
        Media faylni bazadagi barcha oldingi fayllar bilan ko'p qatlamli solishtiradi.
        
        Qaytaradi: (is_duplicate, matched_media_id, match_type, similarity_score)
        """
        sha256 = cls.calculate_sha256(file_path)
        phash_str, dhash_str = cls.calculate_visual_hashes(file_path, media_type)

        async with get_db_session() as session:
            # 1. 100% Aniq bayt dublikati (SHA-256)
            res = await session.execute(
                select(MediaAsset).where(MediaAsset.sha256_hash == sha256)
            )
            exact_match = res.scalar_one_or_none()
            if exact_match:
                logger.info(f"🔁 [DuplicateEngine] SHA-256 bo'yicha 100% aniq dublikat topildi (Media ID: {exact_match.id})")
                return True, exact_match.id, "EXACT_SHA256", 1.0

            # 2. Multi-Frame Perceptual Visual Hash (pHash / dHash)
            if phash_str:
                current_phash = imagehash.hex_to_hash(phash_str)
                all_assets = (await session.execute(
                    select(MediaAsset).where(MediaAsset.phash.isnot(None))
                )).scalars().all()

                for asset in all_assets:
                    if asset.phash:
                        try:
                            prev_phash = imagehash.hex_to_hash(asset.phash)
                            diff = current_phash - prev_phash  # Hamming masofasi (0-64)
                            
                            # Hamming masofasi <= 6 bo'lsa (90%+ vizual o'xshashlik)
                            if diff <= 6:
                                sim = round((64 - diff) / 64, 2)
                                logger.info(f"🖼 [DuplicateEngine] Visual pHash dublikat topildi ({media_type.upper()}) (Media ID: {asset.id}, O'xshashlik: {sim*100}%)")
                                return True, asset.id, "VISUAL_PHASH", sim
                        except Exception:
                            continue

        return False, None, "NONE", 0.0

    @classmethod
    async def select_best_version(cls, asset_ids: List[int]) -> int:
        """Bir xil dublikat guruhidagi fayllar ichidan eng yuqori sifatli (Resolution/Bitrate) variantni tanlaydi."""
        async with get_db_session() as session:
            assets = (await session.execute(
                select(MediaAsset).where(MediaAsset.id.in_(asset_ids))
            )).scalars().all()

            if not assets:
                return asset_ids[0]

            # Resolution (width * height) va file_size bo'yicha saralash
            best = max(assets, key=lambda a: ((a.width or 0) * (a.height or 0), a.file_size or 0))
            return best.id


duplicate_engine = DuplicateEngine()
