"""Dublikat aniqlash: matn hash + rasm perceptual hash."""
from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import imagehash
from PIL import Image

from app.db.repository import Repository

MIN_TEXT_LEN = 25  # bundan qisqa matn hash bilan dublikat deb hisoblanmaydi (masalan "Salom")
DEFAULT_MAX_DISTANCE = 6  # 64-bitli pHash uchun Hamming masofasi

_URL = re.compile(r"(?:https?://|www\.)\S+|\b(?:t\.me|wa\.me)/\S*", re.IGNORECASE)
_MENTION = re.compile(r"@\w+")
_NON_ALNUM = re.compile(r"[\W_]+", re.UNICODE)


def normalize_for_hash(text: str) -> str:
    """Havola, username, tinish belgisi va registrdan qat'i nazar bir xil matn bir xil natija beradi."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = _URL.sub(" ", text)
    text = _MENTION.sub(" ", text)
    return _NON_ALNUM.sub(" ", text).strip()


def text_hash(text: str) -> str | None:
    norm = normalize_for_hash(text)
    if len(norm) < MIN_TEXT_LEN:
        return None
    return hashlib.sha256(norm.encode()).hexdigest()


def image_phash(source: str | Path | bytes | Image.Image) -> str:
    if isinstance(source, (str, Path)):
        img = Image.open(source)
    elif isinstance(source, bytes):
        img = Image.open(io.BytesIO(source))
    else:
        img = source
    return str(imagehash.phash(img.convert("RGB")))


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


@dataclass(frozen=True)
class DuplicateVerdict:
    is_duplicate: bool
    reason: str = ""
    matched_unit_id: int | None = None


async def check_duplicate(
    repo: Repository,
    text: str,
    phashes: list[str],
    exclude_unit_id: int | None = None,
    max_distance: int = DEFAULT_MAX_DISTANCE,
) -> DuplicateVerdict:
    """Matn hash mos kelsa yoki media kadrlarining kamida yarmi ma'lum postga o'xshasa — dublikat."""
    th = text_hash(text)
    if th:
        uid = await repo.find_by_text_hash(th, exclude_unit_id)
        if uid:
            return DuplicateVerdict(True, "text_hash", uid)
    if phashes:
        known = await repo.known_phashes(exclude_unit_id)
        hits: dict[int, int] = {}
        for ph in phashes:
            matched = {uid for uid, kp in known if hamming(ph, kp) <= max_distance}
            for uid in matched:
                hits[uid] = hits.get(uid, 0) + 1
        need = max(1, -(-len(phashes) // 2))
        for uid, n in sorted(hits.items(), key=lambda kv: -kv[1]):
            if n >= need:
                return DuplicateVerdict(True, "media_phash", uid)
    return DuplicateVerdict(False)
