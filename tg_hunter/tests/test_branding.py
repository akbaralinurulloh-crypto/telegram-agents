import pytest
from PIL import Image

from app.llm.base import LLMError
from app.pipeline.branding import remove_branding
from tests.fakes import FakeLLM

CLEAN = {"has_branding": False, "regions": []}
LOGO = {"has_branding": True, "regions": [{"kind": "logo", "box": [50, 700, 150, 950]}]}


def img():
    return Image.new("RGB", (400, 300), (30, 120, 60))


async def test_no_branding_untouched():
    im = img()
    r = await remove_branding(FakeLLM(branding=[CLEAN]), im)
    assert r.status == "ok" and not r.changed and r.image is im


async def test_logo_covered_then_verified():
    llm = FakeLLM(branding=[LOGO, CLEAN])
    im = img()
    px = im.load()
    for x in range(290, 380):  # logotip (och rangli to'rtburchak)
        for y in range(15, 45):
            px[x, y] = (250, 250, 250)
    r = await remove_branding(llm, im)
    assert r.status == "ok" and r.changed and llm.count("BRANDING") == 2
    assert r.image.getpixel((330, 30)) == (30, 120, 60)  # logo o'rniga fon rangi
    assert len(llm.calls[1]["images"]) == 1  # ikkinchi chaqiruv tozalangan rasmni ko'radi


async def test_cover_not_confirmed_is_rejected():
    r = await remove_branding(FakeLLM(branding=[LOGO, LOGO]), img())
    assert r.status == "reject" and r.reason == "branding_cover_failed"


async def test_branding_without_location_rejected():
    r = await remove_branding(FakeLLM(branding=[{"has_branding": True, "regions": []}]), img())
    assert r.status == "reject" and r.reason == "branding_unlocatable"


@pytest.mark.parametrize("bad", [{}, {"has_branding": "false"}, {"has_branding": None}])
async def test_ambiguous_answer_never_passes(bad):
    r = await remove_branding(FakeLLM(branding=[bad]), img())
    assert r.status == "manual_review" and r.reason == "branding_check_ambiguous"


async def test_verification_ambiguous_means_reject():
    r = await remove_branding(FakeLLM(branding=[LOGO, {"has_branding": "no"}]), img())
    assert r.status == "reject"


async def test_llm_error_goes_to_manual_review():
    r = await remove_branding(FakeLLM(branding=[LLMError("429")]), img())
    assert r.status == "manual_review" and r.reason == "branding_check_llm_error"


async def test_huge_logo_rejected():
    big = {"has_branding": True, "regions": [{"kind": "watermark", "box": [0, 0, 1000, 1000]}]}
    r = await remove_branding(FakeLLM(branding=[big]), img())
    assert r.status == "reject" and r.reason == "too_much_overlay"
