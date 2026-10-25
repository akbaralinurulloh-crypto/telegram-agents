import pytest

from app.config import AppConfig
from app.llm.base import LLMError
from app.pipeline.scorer import ScoringError, combine, score_unit
from tests.fakes import FakeLLM

CFG = AppConfig.model_validate({"channel_topic": "Texnologiya yangiliklari"})


def resp(t, q, a, m, **kw):
    return {"topic_fit": t, "quality": q, "audience_interest": a, "media_quality": m, "final_score": 10, "reason": "sabab", "risks": [], **kw}


async def test_weighted_average_with_media():
    # 0.3*8 + 0.25*6 + 0.25*7 + 0.2*9 = 2.4+1.5+1.75+1.8 = 7.45
    r = await score_unit(FakeLLM(scorer=[resp(8, 6, 7, 9)]), CFG, "matn", [b"img"])
    assert r.final_score == 7.45 and r.passed and r.media_quality == 9


async def test_llm_final_score_is_ignored():
    r = await score_unit(FakeLLM(scorer=[resp(1, 1, 1, 1, final_score=10)]), CFG, "matn", [b"i"])
    assert r.final_score == 1 and not r.passed


async def test_media_weight_redistributed_when_no_media():
    # media yo'q: (0.3*8 + 0.25*6 + 0.25*7) / 0.8 = 5.65/0.8 = 7.0625
    r = await score_unit(FakeLLM(scorer=[resp(8, 6, 7, 10)]), CFG, "matn", [])
    assert r.media_quality is None and r.final_score == 7.06 and r.passed


def test_combine_no_media_equals_plain_weights():
    assert combine(CFG, 5, 5, 5, None) == pytest.approx(5)


@pytest.mark.parametrize("score, expected", [(6.9, False), (6.99, False), (7.0, True), (7.1, True)])
async def test_threshold_boundary(score, expected):
    r = await score_unit(FakeLLM(scorer=[resp(score, score, score, score)]), CFG, "matn", [b"i"])
    assert r.passed is expected


async def test_threshold_follows_config():
    cfg = AppConfig.model_validate({"scoring": {"min_score": 8}})
    r = await score_unit(FakeLLM(scorer=[resp(7.5, 7.5, 7.5, 7.5)]), cfg, "x", [b"i"])
    assert not r.passed


@pytest.mark.parametrize("bad", [{"topic_fit": 11}, {"quality": -1}, {"audience_interest": "9"}, {"topic_fit": True}, {"quality": None}])
async def test_invalid_scores_fail_closed(bad):
    with pytest.raises(ScoringError):
        await score_unit(FakeLLM(scorer=[{**resp(8, 8, 8, 8), **bad}]), CFG, "m", [b"i"])


async def test_missing_media_score_ok_when_no_media():
    data = resp(8, 8, 8, 0)
    del data["media_quality"]
    assert (await score_unit(FakeLLM(scorer=[data]), CFG, "m", [])).passed


async def test_llm_error_becomes_scoring_error():
    with pytest.raises(ScoringError):
        await score_unit(FakeLLM(scorer=[LLMError("tarmoq")]), CFG, "m", [])


async def test_topic_and_images_reach_the_model():
    llm = FakeLLM(scorer=[resp(8, 8, 8, 8)])
    await score_unit(llm, CFG, "matn", [b"a", b"b"])
    assert llm.calls[0]["images"] == [b"a", b"b"] and "matn" in llm.calls[0]["user"]
