"""Bitta xabar/albom uchun to'liq oqim: dublikat -> matn tozalash -> media -> baholash -> tozalash -> izoh -> joylash."""
from __future__ import annotations

import asyncio
import io
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from PIL import Image

from app.bot_admin import is_dry_run, is_paused
from app.config import AppConfig
from app.db.models import SourceUnit
from app.db.repository import Repository
from app.llm.base import LLMClient
from app.pipeline.branding import detect_branding, remove_branding
from app.pipeline.captioner import make_caption
from app.pipeline.dedupe import check_duplicate, image_phash, text_hash
from app.pipeline.media_clean import clean_image
from app.pipeline.ocr import OCREngine, default_engines
from app.pipeline.publisher import MediaItem, Publisher, build_plan, message_link
from app.pipeline.scorer import ScoringError, score_unit
from app.pipeline.text_clean import clean_text
from app.pipeline.video_clean import clean_video, sample_frames
from app.utils.logging import get_logger

log = get_logger("pipeline")
PHOTO_MAX_BYTES = 9 * 1024 * 1024


class Transient(Exception):
    """Vaqtincha xato (LLM kvota/503): post yo'qolmaydi, keyinroq qayta uriniladi."""


class Rejected(Exception):
    def __init__(self, state: str, reason: str, **detail):
        self.state, self.reason, self.detail = state, reason, detail


@dataclass
class MediaFile:
    path: Path
    kind: str  # "photo" | "video"


class MediaSource(Protocol):
    async def download(self, unit: SourceUnit, dest: Path, max_video_bytes: int) -> list[MediaFile]:
        """Xabar(lar)dan media yuklaydi. Qo'llab-quvvatlanmaydigan tur: Rejected('rejected','unsupported_media'); katta: 'media_too_large'."""


def _open(path: Path) -> Image.Image:
    """Faylni xotiraga o'qiydi va yopadi (Windows'da vaqtinchalik papkani o'chirishga to'sqinlik qilmasligi uchun)."""
    with Image.open(path) as im:
        im.load()
        return im.copy()


def _jpeg_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=88)
    return buf.getvalue()


def _save_photo(img: Image.Image, dest: Path) -> Path:
    img = img.convert("RGB")
    img.thumbnail((2560, 2560))
    img.save(dest, "JPEG", quality=92)
    return dest


class Pipeline:
    def __init__(
        self,
        repo: Repository,
        llm: LLMClient,
        cfg: AppConfig,
        publisher: Publisher,
        media: MediaSource,
        *,
        target: str,
        admin_id: int,
        dry_run_default: bool = True,
        notify: Callable[[str], Awaitable[None]] | None = None,
        engines: list[OCREngine] | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.repo, self.llm, self.cfg, self.publisher, self.media = repo, llm, cfg, publisher, media
        self.target, self.admin_id, self.dry_run_default = target, admin_id, dry_run_default
        self.notify = notify or (lambda _t: asyncio.sleep(0))
        self.engines = engines
        self._now = now
        self._wake = asyncio.Event()
        self._deferred: dict[int, tuple[int, datetime]] = {}  # unit_id -> (urinish, shu vaqtgacha kutish)
        self.running = True

    # ---------- navbat ----------
    def wake(self) -> None:
        self._wake.set()

    async def run_forever(self) -> None:
        while self.running:
            try:
                if await is_paused(self.repo):
                    await self._sleep_or_wake()
                    continue
                unit = self._next_ready(await self.repo.pending_units())
                if unit is None:
                    await self._sleep_or_wake()
                    continue
                await self.process(unit.id)
            except asyncio.CancelledError:
                raise
            except Exception:  # navbat sikli hech qachon yiqilmasin
                log.exception("worker_loop_error")
                await asyncio.sleep(2)

    async def _sleep_or_wake(self) -> None:
        self._wake.clear()
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=self.cfg.pipeline.poll_seconds)
        except asyncio.TimeoutError:
            pass

    def _next_ready(self, units: list[SourceUnit]) -> SourceUnit | None:
        for u in units:
            wait = self._deferred.get(u.id)
            if wait is None or wait[1] <= self._now():
                return u
        return None

    # ---------- asosiy oqim ----------
    async def process(self, unit_id: int) -> None:
        unit = await self.repo.get_unit(unit_id)
        if unit is None or unit.deleted_at or unit.state not in ("received", "processing"):
            return
        await self.repo.set_state(unit_id, "processing")
        tmp = Path(tempfile.mkdtemp(prefix=f"u{unit_id}_", dir=self._media_dir()))
        try:
            await self._run(unit, tmp)
            await self._ok_streak()
        except Rejected as r:
            await self.repo.record_decision(unit_id, r.state, r.reason, score=r.detail.pop("score", None), detail=r.detail or None)
            log.info("decision", unit_id=unit_id, state=r.state, reason=r.reason)
            await self._ok_streak()
        except Transient as exc:
            await self._defer(unit_id, str(exc))
        except Exception as exc:
            log.exception("unit_failed", unit_id=unit_id)
            await self.repo.record_decision(unit_id, "error", "exception", detail={"error": f"{type(exc).__name__}: {exc}"[:300]})
            await self._count_error()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)  # vaqtinchalik media o'chiriladi

    def _media_dir(self) -> Path:
        d = Path(self.cfg.pipeline.media_dir)
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def _run(self, unit: SourceUnit, tmp: Path) -> None:
        cfg = self.cfg
        # 1. dublikat (matn)
        th = text_hash(unit.text)
        dup = await check_duplicate(self.repo, unit.text, [], exclude_unit_id=unit.id)
        if dup.is_duplicate:
            await self.repo.add_hashes(unit.id, th, [])
            raise Rejected("rejected", "duplicate", matched_unit=dup.matched_unit_id, by=dup.reason)

        # 2. matn: reklama + telefon
        tc = clean_text(unit.text)
        if tc.status != "ok":
            await self.repo.add_hashes(unit.id, th, [])
            raise Rejected("rejected" if tc.status == "reject" else "manual_review", tc.reason or "text_clean")
        text = tc.text

        # 3. media yuklash va dublikat (rasm)
        files = await self.media.download(unit, tmp, int(cfg.media.max_video_mb * 1024 * 1024)) if unit.media_kinds else []
        photos = [_open(f.path) for f in files if f.kind == "photo"]
        videos = [f for f in files if f.kind == "video"]
        keyframes: list[Image.Image] = []
        for v in videos:
            keyframes += await asyncio.to_thread(self._keyframes, v.path, tmp)
        phashes = [image_phash(i) for i in photos + keyframes[:3]]
        await self.repo.add_hashes(unit.id, th, phashes)
        if phashes:
            dup = await check_duplicate(self.repo, "", phashes, exclude_unit_id=unit.id)
            if dup.is_duplicate:
                raise Rejected("rejected", "duplicate", matched_unit=dup.matched_unit_id, by=dup.reason)

        # 4. baholash
        llm_images = [_jpeg_bytes(i) for i in photos + keyframes][: cfg.llm.max_images]
        try:
            score = await score_unit(self.llm, cfg, text, llm_images, has_media=bool(files))
        except ScoringError as exc:
            raise Transient(f"scoring: {exc}") from exc
        if not score.passed:
            raise Rejected("rejected", "low_score", score=score.final_score, reason_text=score.reason, risks=score.risks)

        # 5. media tozalash (raqam, reklama, logotip)
        out_media: list[MediaItem] = []
        clean_llm_images: list[bytes] = []
        for i, f in enumerate(files):
            if f.kind == "photo":
                item, img_bytes = await self._clean_photo(f, tmp, i, score.final_score)
                out_media.append(item)
                clean_llm_images.append(img_bytes)
            else:
                item = await self._clean_video(f, tmp, i, score.final_score)
                out_media.append(item)
        if keyframes and not clean_llm_images:
            clean_llm_images = [_jpeg_bytes(k) for k in keyframes[:3]]

        # 6. izoh (faqat media bor postlar uchun)
        caption = ""
        if out_media:
            cr = await make_caption(self.llm, cfg, text, clean_llm_images[: cfg.llm.max_images])
            if not cr.ok:
                if cr.reason == "llm_error":
                    raise Transient(f"caption: {cr.problems}")
                raise Rejected("rejected", cr.reason or "caption_failed", score=score.final_score, problems=cr.problems)
            caption = cr.caption

        # 7. joylash
        plan = build_plan(text, caption, out_media)
        if not plan.media and not plan.text:
            raise Rejected("rejected", "empty_post", score=score.final_score)
        dry = await is_dry_run(self.repo, self.dry_run_default)
        if dry:
            await self.publisher.publish(self.admin_id, type(plan)([], text=f"🧪 DRY-RUN #{unit.id} | ball {score.final_score} | {unit.channel_title}\nSabab: {score.reason}\nPastdagi post kanalga joylanADI (hozir faqat sizga ko'rsatildi):"))
            await self.publisher.publish(self.admin_id, plan)
            await self.repo.record_decision(unit.id, "dryrun", None, score=score.final_score, caption=caption, dry_run=True)
        else:
            ids = await self.publisher.publish(self.target, plan)
            await self.repo.record_decision(unit.id, "posted", None, score=score.final_score, caption=caption, posted_ids=ids)
            log.info("posted", unit_id=unit.id, link=message_link(self.target, ids[0]))

    # ---------- media bosqichlari ----------
    def _keyframes(self, path: Path, tmp: Path) -> list[Image.Image]:
        from app.pipeline.video_clean import probe

        dur = max(probe(path).duration, 0.5)
        n = 4
        d = tmp / f"kf_{path.stem}"
        d.mkdir(exist_ok=True)
        return [im for _, im in sample_frames(path, dur / n, dur / (2 * n), d)][:n]

    async def _clean_photo(self, f: MediaFile, tmp: Path, idx: int, score: float) -> tuple[MediaItem, bytes]:
        img = _open(f.path)
        r = await asyncio.to_thread(clean_image, img, self.engines or default_engines(), self.cfg.media.max_cover_fraction)
        if r.status != "ok":
            raise Rejected("rejected" if r.status == "reject" else "manual_review", r.reason or "image_clean", score=score)
        out = r.image
        if self.cfg.media.logo_check:
            b = await remove_branding(self.llm, out, self.cfg.media.max_cover_fraction)
            if b.reason == "branding_check_llm_error":
                raise Transient("branding check")
            if b.status != "ok":
                raise Rejected("rejected" if b.status == "reject" else "manual_review", b.reason or "branding", score=score)
            out = b.image
        if not r.changed and out is r.image and f.path.stat().st_size <= PHOTO_MAX_BYTES:
            path = f.path  # o'zgarmagan — asl faylni qayta siqmaymiz
        else:
            path = _save_photo(out, tmp / f"clean_{idx}.jpg")
        return MediaItem(path, "photo"), _jpeg_bytes(out)

    async def _clean_video(self, f: MediaFile, tmp: Path, idx: int, score: float) -> MediaItem:
        m = self.cfg.media
        r = await asyncio.to_thread(
            clean_video, f.path, tmp / f"clean_{idx}.mp4", self.engines or default_engines(),
            sample_interval=m.sample_interval, max_frames=m.max_frames, max_seconds=m.max_video_seconds,
            max_mb=m.max_video_mb, max_cover_fraction=m.max_cover_fraction,
        )
        if r.status != "ok":
            raise Rejected("rejected" if r.status == "reject" else "manual_review", r.reason or "video_clean", score=score)
        if m.logo_check:  # videoda logotipni qoplamaymiz: aniqlansa — qo'lda ko'rib chiqish (fail-closed)
            frames = await asyncio.to_thread(self._keyframes, r.path, tmp)
            try:
                flag, _ = await detect_branding(self.llm, frames[:3])
            except Exception as exc:
                raise Transient(f"video branding: {exc}") from exc
            if flag is not False:
                raise Rejected("manual_review", "video_branding_detected", score=score)
        return MediaItem(r.path, "video")

    # ---------- xatolar, kill switch ----------
    async def _defer(self, unit_id: int, why: str) -> None:
        tries = self._deferred.get(unit_id, (0, self._now()))[0] + 1
        if tries >= self.cfg.pipeline.defer_max_attempts:
            self._deferred.pop(unit_id, None)
            await self.repo.record_decision(unit_id, "error", "llm_error", detail={"error": why[:300], "attempts": tries})
            await self._count_error()
            return
        minutes = min(self.cfg.pipeline.defer_base_minutes * 2 ** (tries - 1), 30)
        self._deferred[unit_id] = (tries, self._now() + timedelta(minutes=minutes))
        await self.repo.set_state(unit_id, "received")
        log.warning("deferred", unit_id=unit_id, attempt=tries, minutes=minutes, why=why[:120])

    async def _ok_streak(self) -> None:
        if (await self.repo.get_kv("consecutive_errors", "0")) != "0":
            await self.repo.set_kv("consecutive_errors", "0")

    async def _count_error(self) -> None:
        n = int(await self.repo.get_kv("consecutive_errors", "0") or 0) + 1
        await self.repo.set_kv("consecutive_errors", str(n))
        if n >= self.cfg.kill_switch.max_consecutive_errors:
            await self.repo.set_kv("paused", "1")
            await self.repo.audit("kill_switch", errors=n)
            await self.notify(f"🛑 KILL SWITCH: ketma-ket {n} ta xato. Agent pauzaga qo'yildi. Sababni /last va loglardan ko'ring, so'ng /resume.")
