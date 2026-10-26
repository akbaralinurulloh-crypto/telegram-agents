import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image

from app.bot_admin import DRYRUN, PAUSED
from app.config import load_app_config
from app.db.repository import NormalizedUnit
from app.llm.base import LLMError
from app.pipeline.ocr import default_engines
from app.pipeline.publisher import PostPlan
from app.pipeline.runner import MediaFile, Pipeline, Rejected
from tests.fakes import GOOD_VERDICT, FakeLLM
from tests.media_helpers import TARGET, make_image, ocr_digit_strings

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
CLEAN = {"has_branding": False, "regions": []}
TEXT = "Toshkentda yangi metro bekati ochildi. Bekat 15 may kuni yo'lovchilarni qabul qila boshlaydi."


def scored(t=9, q=9, a=9, m=9):
    return {"topic_fit": t, "quality": q, "audience_interest": a, "media_quality": m, "reason": "mos", "risks": []}


class NoTextEngine:
    name = "none"

    def read(self, img):
        return []


class FakeMedia:
    def __init__(self, images=None, videos=None, error=None):
        self.images, self.error, self.calls = images or [], error, 0

    async def download(self, unit, dest, max_video_bytes):
        self.calls += 1
        if self.error:
            raise self.error
        out = []
        for i, img in enumerate(self.images):
            p = Path(dest) / f"src_{i}.jpg"
            img.save(p, "JPEG")
            out.append(MediaFile(p, "photo"))
        return out


class FakePublisher:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    async def publish(self, chat_id, plan: PostPlan):
        if self.fail:
            raise self.fail
        self.calls.append((chat_id, plan, [m.path.read_bytes() if m.path.exists() else b"" for m in plan.media]))
        return [500 + len(self.calls)]

    def to(self, chat):
        return [c for c in self.calls if c[0] == chat]


@pytest.fixture
def cfg(tmp_path):
    c = load_app_config("config.yaml")
    c.channel_topic = "Umra va ziyorat"
    c.pipeline.media_dir = str(tmp_path / "media")
    c.pipeline.poll_seconds = 0.05
    c.kill_switch.max_consecutive_errors = 3
    return c


class Env:
    def __init__(self, repo, cfg, llm, media=None, pub=None, engines=None):
        self.repo, self.cfg, self.llm = repo, cfg, llm
        self.media, self.pub = media or FakeMedia(), pub or FakePublisher()
        self.notes = []

        async def notify(t):
            self.notes.append(t)

        self.p = Pipeline(repo, llm, cfg, self.pub, self.media, target="@kanal", admin_id=42, dry_run_default=True, notify=notify, engines=engines or [NoTextEngine()])
        self.mid = 0

    async def add(self, text=TEXT, kinds=()):
        self.mid += 1
        u, _ = await self.repo.add_unit(NormalizedUnit(-100, "Manba1", [self.mid], None, text, list(kinds), NOW))
        return u.id

    async def run(self, uid):
        await self.p.process(uid)
        return await self.repo.get_unit(uid)

    async def live(self):
        await self.repo.set_kv(DRYRUN, "0")


@pytest.fixture
def env(repo, cfg):
    def make(**llm_kw):
        llm = FakeLLM(**{"scorer": [scored()], "captioner": [{"caption": "Toshkentda yangi metro bekati ochildi."}], "validator": [GOOD_VERDICT], "branding": [CLEAN], **llm_kw})
        return Env(repo, cfg, llm)

    return make


async def test_text_post_default_is_dry_run_and_goes_to_admin(env):
    e = env()
    u = await e.run(await e.add())
    assert u.state == "dryrun" and u.dry_run and u.score == 9.0
    assert [c[0] for c in e.pub.calls] == [42, 42] and "DRY-RUN" in e.pub.calls[0][1].text
    assert e.pub.calls[1][1].text == TEXT and not e.pub.to("@kanal")
    assert e.llm.count("CAPTIONER") == 0  # matn-only postga izoh yozilmaydi


async def test_live_text_post_published_to_channel(env):
    e = env()
    await e.live()
    u = await e.run(await e.add())
    assert u.state == "posted" and u.posted_ids == [501] and e.pub.to("@kanal")[0][1].text == TEXT


async def test_phone_in_text_is_replaced_before_publishing(env):
    e = env()
    await e.live()
    u = await e.run(await e.add("Yangi markaz ochildi.\nAloqa: +998 90 123 45 67\nObuna bo'ling @kanal_x"))
    assert u.state == "posted"
    assert e.pub.to("@kanal")[0][1].text == "Yangi markaz ochildi.\nAloqa: 88 832 77 00"


async def test_photo_post_gets_caption_and_media_published(env, tmp_path):
    e = env()
    e.media.images = [make_image([], bg=(30, 120, 60))]
    await e.live()
    u = await e.run(await e.add(kinds=["photo"]))
    assert u.state == "posted" and u.caption == "Toshkentda yangi metro bekati ochildi."
    chat, plan, blobs = e.pub.to("@kanal")[0]
    assert plan.media[0].kind == "photo" and plan.caption == f"{TEXT}\n\n{u.caption}" and blobs[0]
    assert e.llm.count("BRANDING") == 1
    assert not any((tmp_path / "media").iterdir())  # vaqtinchalik fayllar o'chirilgan


async def test_low_score_rejected_with_reason_and_not_published(env):
    e = env(scorer=[scored(6, 6, 6, 6)])
    await e.live()
    u = await e.run(await e.add())
    assert u.state == "rejected" and u.decision_reason == "low_score" and u.score == 6.0 and not e.pub.calls


@pytest.mark.parametrize("v, state", [(6.9, "rejected"), (7.0, "posted")])
async def test_threshold_end_to_end(env, v, state):
    e = env(scorer=[scored(v, v, v, v)])
    await e.live()
    assert (await e.run(await e.add())).state == state


async def test_duplicate_text_rejected(env):
    e = env()
    await e.live()
    assert (await e.run(await e.add())).state == "posted"
    u = await e.run(await e.add(TEXT + " https://t.me/x"))
    assert u.state == "rejected" and u.decision_reason == "duplicate" and len(e.pub.to("@kanal")) == 1


async def test_duplicate_image_rejected(env):
    e = env()
    await e.live()
    img = make_image([], bg=(10, 80, 150))
    e.media.images = [img]
    assert (await e.run(await e.add("Birinchi post matni alohida", ["photo"]))).state == "posted"
    e.media.images = [img.resize((300, 200))]
    u = await e.run(await e.add("Boshqa matn butunlay boshqacha", ["photo"]))
    assert u.state == "rejected" and u.decision_reason == "duplicate"


async def test_commercial_ad_rejected_before_any_llm_call(env):
    e = env()
    u = await e.run(await e.add("Telefon sotiladi, chegirma 20% gacha!"))
    assert u.state == "rejected" and u.decision_reason == "commercial_ad" and not e.llm.calls


async def test_uncertain_phone_goes_to_manual_review(env):
    e = env()
    u = await e.run(await e.add("Yangilik matni. Tel: 123 456 78"))
    assert u.state == "manual_review" and u.decision_reason == "phone_uncertain" and not e.pub.calls


async def test_hadith_caption_cancels_post(env):
    e = env(captioner=[{"caption": "Hadisda aytilishicha, sabr yaxshi."}])
    e.media.images = [make_image([])]
    await e.live()
    u = await e.run(await e.add("Payg'ambar alayhissalom dedilar: sabr qiling.", ["photo"]))
    assert u.state == "rejected" and u.decision_reason == "hadis_validator" and not e.pub.calls


async def test_fabricated_fact_blocked(env):
    e = env(captioner=[{"caption": "Bekat 500 million dollarga qurildi."}])
    e.media.images = [make_image([])]
    u = await e.run(await e.add(kinds=["photo"]))
    assert u.state == "rejected" and u.decision_reason == "fact_validator"


async def test_unsupported_media_rejected(env):
    e = env()
    e.media.error = Rejected("rejected", "unsupported_media", kind="audio")
    u = await e.run(await e.add(kinds=["audio"]))
    assert u.state == "rejected" and u.decision_reason == "unsupported_media"


async def test_llm_outage_defers_then_gives_up(env, cfg):
    cfg.pipeline.defer_max_attempts = 3
    e = env(scorer=[LLMError("429 quota")])
    uid = await e.add()
    for _ in range(2):
        assert (await e.run(uid)).state == "received"  # post yo'qolmadi, keyinroq qayta uriniladi
        assert e.p._next_ready([await e.repo.get_unit(uid)]) is None  # kutish vaqti tugamaguncha olinmaydi
        e.p._deferred[uid] = (e.p._deferred[uid][0], datetime.now(timezone.utc) - timedelta(seconds=1))
    u = await e.run(uid)
    assert u.state == "error" and u.decision_reason == "llm_error"


async def test_kill_switch_pauses_and_notifies(env, cfg):
    e = env(scorer=[LLMError("down")])
    cfg.pipeline.defer_max_attempts = 1
    for i in range(3):
        await e.run(await e.add(f"Har xil matn raqami {i} uchun alohida yangilik mazmuni"))
    assert await e.repo.get_kv(PAUSED) == "1" and any("KILL SWITCH" in n for n in e.notes)


async def test_success_resets_error_streak(env):
    e = env()
    await e.repo.set_kv("consecutive_errors", "2")
    await e.run(await e.add())
    assert await e.repo.get_kv("consecutive_errors") == "0"


async def test_publisher_failure_is_recorded_as_error(env):
    e = env()
    e.pub.fail = RuntimeError("telegram down")
    await e.live()
    u = await e.run(await e.add())
    assert u.state == "error" and u.decision_reason == "exception" and "telegram down" in u.decision_detail["error"]
    assert await e.repo.get_kv("consecutive_errors") == "1"


async def test_deleted_unit_is_skipped(env):
    e = env()
    uid = await e.add()
    await e.repo.mark_deleted([e.mid], -100)
    assert (await e.run(uid)).state == "received" and not e.llm.calls


async def test_worker_loop_respects_pause_and_resume(env):
    e = env()
    await e.live()
    await e.repo.set_kv(PAUSED, "1")
    uid = await e.add()
    task = asyncio.create_task(e.p.run_forever())
    await asyncio.sleep(0.3)
    assert (await e.repo.get_unit(uid)).state == "received"
    await e.repo.set_kv(PAUSED, "0")
    e.p.wake()
    for _ in range(40):
        await asyncio.sleep(0.1)
        if (await e.repo.get_unit(uid)).state == "posted":
            break
    e.p.running = False
    task.cancel()
    assert (await e.repo.get_unit(uid)).state == "posted"


async def test_real_ocr_replaces_number_on_published_photo(env):
    e = Env(env().repo, env().cfg, FakeLLM(scorer=[scored()], captioner=[{"caption": "Ziyorat joyi lavhasi."}], validator=[GOOD_VERDICT], branding=[CLEAN]), engines=default_engines())
    e.media.images = [make_image([("Aloqa: +998 90 123 45 67", (30, 120), 36, (255, 255, 255))])]
    await e.live()
    u = await e.run(await e.add("Umra safari", ["photo"]))
    assert u.state == "posted", (u.state, u.decision_reason)
    published = e.pub.to("@kanal")[0][2][0]
    import io

    digits = ocr_digit_strings(Image.open(io.BytesIO(published)))
    assert not any("901234567" in d for d in digits) and any(TARGET in d for d in digits)


async def test_failed_unit_does_not_block_its_copy(env):
    """Xatoga tushgan post nusxasini 'dublikat' deb to'smasligi kerak."""
    e = env()
    e.pub.fail = RuntimeError("telegram down")
    await e.live()
    assert (await e.run(await e.add())).state == "error"
    e.pub.fail = None
    assert (await e.run(await e.add(TEXT + " https://t.me/x"))).state == "posted"
