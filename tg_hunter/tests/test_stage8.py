import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

from app.pipeline.runner import MediaFile
from app.pipeline.video_clean import compress_to_fit, probe
from app.reports.scheduler import HEARTBEAT_KEY, downtime_notice, heartbeat
from tests.fakes import GOOD_VERDICT, FakeLLM
from tests.test_runner import CLEAN, TEXT, Env, FakeMedia, cfg, scored  # noqa: F401  (cfg fixture)
from tests.video_helpers import H, W, make_video

TZ = ZoneInfo("Asia/Tashkent")


def noise_video(path: Path, secs=3):
    rng = random.Random(1)
    return make_video(path, secs, lambda i, t: Image.effect_noise((W, H), 80 + rng.randint(0, 20)))


# ---------- video siqish ----------
def test_compress_big_video_to_fit(tmp_path):
    src = noise_video(tmp_path / "big.mp4")
    cap = 1 * 1024 * 1024
    assert src.stat().st_size > cap
    out = compress_to_fit(src, tmp_path / "fit.mp4", cap)
    assert out is not None and out.stat().st_size <= cap
    assert abs(probe(out).duration - probe(src).duration) < 0.5  # davomiyligi saqlangan


def test_small_video_returned_untouched(tmp_path):
    src = noise_video(tmp_path / "s.mp4", secs=1)
    assert compress_to_fit(src, tmp_path / "x.mp4", 50 * 1024 * 1024) == src


def test_impossible_fit_returns_none(tmp_path):
    src = noise_video(tmp_path / "b.mp4")
    assert compress_to_fit(src, tmp_path / "x.mp4", 20 * 1024) is None  # sifat yaroqsiz bo'lardi
    assert not (tmp_path / "x.mp4").exists()


class VideoMedia(FakeMedia):
    def __init__(self, video: Path):
        super().__init__()
        self.video = video

    async def download(self, unit, dest, max_video_bytes):
        p = Path(dest) / "src.mp4"
        p.write_bytes(self.video.read_bytes())
        return [MediaFile(p, "video")]


async def test_big_video_is_compressed_not_rejected(repo, cfg, tmp_path):
    cfg.media.max_video_mb = 1.0
    cfg.media.max_download_mb = 50
    llm = FakeLLM(scorer=[scored()], captioner=[{"caption": "Toshkentda yangi metro bekati ochildi."}], validator=[GOOD_VERDICT], branding=[CLEAN])
    e = Env(repo, cfg, llm, media=VideoMedia(noise_video(tmp_path / "v.mp4")))
    await e.live()
    u = await e.run(await e.add(TEXT, ["video"]))
    assert u.state == "posted", (u.state, u.decision_reason)
    plan = e.pub.to("@kanal")[0][1]
    assert plan.media[0].kind == "video"
    assert len(e.pub.to("@kanal")[0][2][0]) <= 1 * 1024 * 1024  # yuborilgan fayl chegaradan oshmaydi


async def test_unfittable_video_still_rejected(repo, cfg, tmp_path):
    cfg.media.max_video_mb = 0.02
    cfg.media.max_download_mb = 50
    llm = FakeLLM(scorer=[scored()], captioner=[{"caption": "x"}], validator=[GOOD_VERDICT], branding=[CLEAN])
    e = Env(repo, cfg, llm, media=VideoMedia(noise_video(tmp_path / "v.mp4")))
    u = await e.run(await e.add(TEXT, ["video"]))
    assert u.state == "rejected" and u.decision_reason == "media_too_large"


# ---------- DRY-RUN da rad sabablari ko'rinadi ----------
async def test_dryrun_tells_admin_about_rejects(repo, cfg):
    e = Env(repo, cfg, FakeLLM(scorer=[scored()]))
    await e.run(await e.add("Yangi telefon sotiladi, chegirma 20% gacha, aksiya faqat bugun!"))
    assert any("❌" in n and "commercial_ad" in n and "Manba1" in n for n in e.notes)


async def test_live_mode_does_not_spam_rejects(repo, cfg):
    e = Env(repo, cfg, FakeLLM(scorer=[scored()]))
    await e.live()
    await e.run(await e.add("Yangi telefon sotiladi, chegirma 20% gacha, aksiya faqat bugun!"))
    assert e.notes == []


async def test_reject_notice_can_be_disabled(repo, cfg):
    cfg.pipeline.notify_rejects_in_dryrun = False
    e = Env(repo, cfg, FakeLLM(scorer=[scored()]))
    await e.run(await e.add("Yangi telefon sotiladi, chegirma 20% gacha, aksiya faqat bugun!"))
    assert e.notes == []


async def test_dryrun_reject_shows_score(repo, cfg):
    e = Env(repo, cfg, FakeLLM(scorer=[scored(3, 3, 3, 3)]))
    await e.run(await e.add())
    assert any("low_score" in n and "ball 3.0" in n for n in e.notes)


# ---------- o'chiq turganlik haqida ogohlantirish ----------
async def test_downtime_notice(repo):
    now = datetime(2026, 11, 2, 20, 0, tzinfo=timezone.utc)
    assert await downtime_notice(repo, now, TZ) is None  # birinchi ishga tushish
    await repo.set_kv(HEARTBEAT_KEY, (now - timedelta(minutes=3)).isoformat())
    assert await downtime_notice(repo, now, TZ) is None  # qisqa uzilish — ogohlantirmaydi
    await repo.set_kv(HEARTBEAT_KEY, (now - timedelta(hours=3)).isoformat())
    assert "3.0 soat" in await downtime_notice(repo, now, TZ)
    await repo.set_kv(HEARTBEAT_KEY, (now - timedelta(days=6)).isoformat())
    text = await downtime_notice(repo, now, TZ)
    assert "6.0 kun" in text and "o'tkazib yuborilgan" in text and "VPS" in text


async def test_heartbeat_writes_timestamp(repo):
    await heartbeat(repo)
    raw = await repo.get_kv(HEARTBEAT_KEY)
    assert abs((datetime.now(timezone.utc) - datetime.fromisoformat(raw)).total_seconds()) < 5


# ---------- shovqin himoyasi ----------
async def test_short_chatter_rejects_are_not_announced(repo, cfg):
    e = Env(repo, cfg, FakeLLM(scorer=[scored(2, 2, 2, 2)]))
    await e.run(await e.add("Salom, rahmat"))
    assert e.notes == []  # qisqa yozishma — shovqin
    assert (await repo.last_units(1))[0].decision_reason == "low_score"  # lekin baribir hisobga olinadi


async def test_reject_notices_are_capped_per_hour(repo, cfg):
    cfg.pipeline.max_reject_notices_per_hour = 3
    e = Env(repo, cfg, FakeLLM(scorer=[scored(2, 2, 2, 2)]))
    for i in range(6):
        await e.run(await e.add(f"Bu uzun yozishma raqami {i}, mavzuga aloqasi yo'q oddiy gaplar mazmuni"))
    assert len(e.notes) == 3
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    e.p._now = lambda: later  # soatlik oyna o'tdi — yana ko'rsatiladi
    await e.run(await e.add("Yana bir uzun yozishma, mavzuga aloqasi yo'q boshqa oddiy gaplar"))
    assert len(e.notes) == 4
