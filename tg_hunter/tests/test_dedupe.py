import random
from datetime import datetime, timezone

from PIL import Image

from app.db.repository import NormalizedUnit
from app.pipeline.dedupe import check_duplicate, hamming, image_phash, normalize_for_hash, text_hash

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
LONG = "O'zbekistonda yangi texnologiyalar parki ochildi va minglab yosh mutaxassislar ishga olinadi"


def make_image(seed: int, size=(200, 200)) -> Image.Image:
    """Seed bo'yicha tasodifiy 8x8 rangli bloklar: turli seedlar pHash bo'yicha aniq farq qiladi."""
    rng = random.Random(seed)
    small = Image.new("RGB", (8, 8))
    small.putdata([tuple(rng.randrange(256) for _ in range(3)) for _ in range(64)])
    return small.resize(size, Image.NEAREST)


async def add(repo, mid, text="", phashes=()):
    u, _ = await repo.add_unit(NormalizedUnit(-1, "S", [mid], None, text, [], NOW))
    await repo.add_hashes(u.id, text_hash(text), list(phashes))
    return u


def test_text_hash_ignores_links_case_punctuation_and_mentions():
    a = text_hash(LONG + " https://t.me/abc @kanal")
    b = text_hash(LONG.upper() + "!!!")
    assert a == b and a is not None


def test_short_text_never_hashed():
    assert text_hash("Salom!") is None


def test_normalize():
    assert normalize_for_hash("Hello,   WORLD!! t.me/x") == "hello world"


def test_phash_robust_to_recompression_and_resize():
    img = make_image(1)
    small = img.resize((120, 120))
    other = make_image(3)
    assert hamming(image_phash(img), image_phash(small)) <= 6
    assert hamming(image_phash(img), image_phash(other)) > 6


async def test_text_duplicate(repo):
    first = await add(repo, 1, LONG)
    v = await check_duplicate(repo, LONG + " @ad", [])
    assert v.is_duplicate and v.reason == "text_hash" and v.matched_unit_id == first.id


async def test_not_duplicate_when_text_differs(repo):
    await add(repo, 1, LONG)
    assert not (await check_duplicate(repo, LONG + " boshqa yangilik haqida batafsil ma'lumot", [])).is_duplicate


async def test_image_duplicate(repo):
    ph = image_phash(make_image(1))
    first = await add(repo, 1, "", [ph])
    v = await check_duplicate(repo, "", [image_phash(make_image(1).resize((150, 150)))])
    assert v.is_duplicate and v.reason == "media_phash" and v.matched_unit_id == first.id


async def test_album_needs_half_of_images_to_match(repo):
    a, b, c, d = (image_phash(make_image(i)) for i in (1, 2, 3, 4))
    await add(repo, 1, "", [a, b])
    assert (await check_duplicate(repo, "", [a, b, c, d])).is_duplicate  # 2 / 4
    assert not (await check_duplicate(repo, "", [a, c, d, image_phash(make_image(5))])).is_duplicate  # 1 / 4


async def test_unit_excludes_itself(repo):
    u = await add(repo, 1, LONG)
    assert not (await check_duplicate(repo, LONG, [], exclude_unit_id=u.id)).is_duplicate
