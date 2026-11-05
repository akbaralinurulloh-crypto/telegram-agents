import re
import subprocess

import pytest
from PIL import Image

from app.pipeline.video_clean import clean_video, probe, sample_frames
from tests.media_helpers import TARGET, ocr_digit_strings, ocr_text
from tests.video_helpers import background, make_video, with_text

ORIG = "901234567"


def frames_of(path, step=0.4, offset=0.2, tmp=None):
    return sample_frames(path, step, offset, tmp)


def digits_all(path, tmp_path):
    return [(t, ocr_digit_strings(img), ocr_text(img)) for t, img in frames_of(path, tmp=tmp_path)]


def test_static_number_whole_video(tmp_path):
    src = make_video(tmp_path / "a.mp4", 3, lambda i, t: with_text(with_text(background(t), "Umra safari", (30, 30)), "Tel: +998 90 123 45 67", (30, 190)))
    r = clean_video(src, tmp_path / "a_out.mp4")
    assert r.status == "ok" and r.changed and r.new_number_verified
    frames = digits_all(r.path, tmp_path)
    assert len(frames) >= 6
    assert not any(ORIG in s for _, ds, _ in frames for s in ds)  # har bir kadrda asl raqam yo'q
    assert sum(any(TARGET in s for s in ds) for _, ds, _ in frames) >= len(frames) * 0.7  # yangi raqam o'qiladi
    assert all("Umra" in txt for _, _, txt in frames)  # qolgan mazmun saqlangan


def test_number_only_in_end_card(tmp_path):
    def fn(i, t):
        img = background(t)
        return with_text(img, "Tel: 90 123 45 67", (30, 120), 36) if t >= 1.8 else with_text(img, "Umra safari", (30, 30))

    src = make_video(tmp_path / "b.mp4", 3, fn)
    r = clean_video(src, tmp_path / "b_out.mp4")
    assert r.status == "ok" and r.changed
    frames = digits_all(r.path, tmp_path)
    assert not any(ORIG in s for _, ds, _ in frames for s in ds)
    early = [txt for t, _, txt in frames if t < 1.2]
    assert early and all("Umra" in x for x in early)  # boshida hech narsa qoplanmagan


def test_username_watermark_removed_in_all_frames(tmp_path):
    src = make_video(tmp_path / "c.mp4", 3, lambda i, t: with_text(with_text(background(t), "Yangi bekat ochildi", (30, 40)), "@mening_kanal", (250, 220), 28, (255, 230, 0)))
    r = clean_video(src, tmp_path / "c_out.mp4")
    assert r.status == "ok" and r.changed
    frames = digits_all(r.path, tmp_path)
    assert all("mening" not in txt for _, _, txt in frames)
    assert all("bekat" in txt for _, _, txt in frames)


def test_number_and_cta_together(tmp_path):
    src = make_video(
        tmp_path / "d.mp4", 3,
        lambda i, t: with_text(with_text(with_text(background(t), "Umra narxlari", (30, 20)), "Aloqa: +998 91 765 43 21", (30, 110), 30), "Obuna bo'ling", (30, 200), 30, (255, 230, 0)),
    )
    r = clean_video(src, tmp_path / "d_out.mp4")
    assert r.status == "ok" and r.changed
    frames = digits_all(r.path, tmp_path)
    assert not any("917654321" in s for _, ds, _ in frames for s in ds)
    assert all("Obuna" not in txt for _, _, txt in frames)


def test_moving_number_is_rejected(tmp_path):
    def fn(i, t):
        return with_text(background(t), "Tel: 90 123 45 67", (int(-250 + 220 * t), 120), 34)  # chapdan o'ngga suriladi

    src = make_video(tmp_path / "e.mp4", 3, fn)
    r = clean_video(src, tmp_path / "e_out.mp4")
    # Muhim: hech qachon "ok" emas (post joylanmaydi). Sabab: harakat, qoplash yetmadi yoki kadr chetida kesilgan raqam.
    assert r.status in ("reject", "manual_review")
    assert r.reason in ("moving_overlay", "cover_failed", "phone_uncertain_in_video")
    assert not r.changed or r.status != "ok"


def test_clean_video_passes_unchanged(tmp_path):
    src = make_video(tmp_path / "f.mp4", 2, lambda i, t: with_text(background(t), "Madinadan lavhalar", (30, 100)))
    r = clean_video(src, tmp_path / "f_out.mp4")
    assert r.status == "ok" and not r.changed and r.path == src


def test_audio_track_preserved(tmp_path):
    src = make_video(tmp_path / "g.mp4", 2, lambda i, t: with_text(background(t), "Tel: +998 90 123 45 67", (30, 100), 34), with_audio=True)
    assert probe(src).has_audio
    r = clean_video(src, tmp_path / "g_out.mp4")
    assert r.status == "ok" and probe(r.path).has_audio


def test_uncertain_number_manual_review(tmp_path):
    src = make_video(tmp_path / "h.mp4", 2, lambda i, t: with_text(background(t), "Tel: 123 456 78", (30, 100), 36))
    r = clean_video(src, tmp_path / "h_out.mp4")
    assert r.status == "manual_review" and r.reason == "phone_uncertain_in_video"


def test_limits(tmp_path):
    src = make_video(tmp_path / "i.mp4", 2, lambda i, t: background(t))
    assert clean_video(src, tmp_path / "x.mp4", max_seconds=1).reason == "video_duration_unsupported"
    assert clean_video(src, tmp_path / "y.mp4", max_mb=0.000001).reason == "video_too_large"
