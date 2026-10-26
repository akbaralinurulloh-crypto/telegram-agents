import pytest

from app.pipeline.media_clean import clean_image, fix_ocr_digits
from app.pipeline.ocr import OCREngine, OCRLine, OCRWord
from tests.media_helpers import TARGET, make_image, ocr_digit_strings, ocr_text

W, K = (255, 255, 255), (0, 0, 0)

# (matn, asl raqamning raqamlari, shrift, fon, matn rangi)
PHONE_IMAGES = [
    ("+998 90 123 45 67", "998901234567", 34, (40, 90, 160), W),
    ("Tel: 90 123 45 67", "901234567", 34, W, K),
    ("998901234567", "998901234567", 34, (20, 20, 20), (255, 220, 0)),
    ("(90) 123-45-67", "901234567", 34, (230, 230, 230), (20, 20, 120)),
    ("+7 495 123 45 67", "74951234567", 34, (120, 30, 30), W),
    ("90-123-45-67", "901234567", 34, (30, 110, 60), W),
    ("Aloqa: +998 91 765 43 21", "998917654321", 26, (245, 240, 220), (60, 20, 20)),
    ("+998(90)1234567", "998901234567", 36, (10, 10, 60), (200, 230, 255)),
    ("Tel: +998 93 555 12 34", "998935551234", 44, W, (160, 0, 0)),
    ("90 123 45 67", "901234567", 28, (200, 120, 20), K),
    ("+998 97 888 99 00", "998978889900", 58, (0, 70, 90), W),
]


@pytest.mark.parametrize("text, digits, fs, bg, fg", PHONE_IMAGES)
def test_phone_in_image_replaced_and_verified(text, digits, fs, bg, fg):
    img = make_image([("Umra safari", (30, 30), 30, fg), (text, (30, 140), fs, fg)], bg=bg)
    r = clean_image(img)
    assert r.status == "ok", (r.status, r.reason)
    assert r.changed and r.new_number_verified
    strings = ocr_digit_strings(r.image)  # mustaqil qayta OCR
    assert not any(digits in s for s in strings), strings  # asl raqam ko'rinmaydi
    assert any(TARGET in s for s in strings), strings  # yangi raqam o'qiladi
    assert "Umra" in ocr_text(r.image)  # qolgan matn buzilmagan


def test_two_numbers_in_one_image():
    img = make_image([("Ali: 90 123 45 67", (30, 40), 32, W), ("Vali: +998 91 765 43 21", (30, 140), 32, W)])
    r = clean_image(img)
    assert r.status == "ok"
    s = ocr_digit_strings(r.image)
    assert not any("901234567" in x or "917654321" in x for x in s)
    assert sum(TARGET in x for x in s) >= 2


def test_noisy_background_never_leaks():
    img = make_image([("Tel: +998 90 123 45 67", (30, 120), 36, W)], bg=(90, 90, 90), noise=45)
    r = clean_image(img)
    if r.status == "ok":  # ok bo'lsa — haqiqatan toza bo'lishi shart
        assert not any("901234567" in s for s in ocr_digit_strings(r.image))
    else:
        assert r.status in ("reject", "manual_review")


@pytest.mark.parametrize("text, forbidden", [("@mening_kanal", "mening"), ("t.me/mening_kanal", "mening"), ("Obuna bo'ling", "Obuna")])
def test_ad_text_covered(text, forbidden):
    img = make_image([("Yangi bekat ochildi", (30, 40), 32, W), (text, (30, 200), 32, (255, 230, 0))])
    r = clean_image(img)
    assert r.status == "ok" and r.changed, (r.status, r.reason)
    out = ocr_text(r.image)
    assert forbidden not in out and "bekat" in out


def test_price_and_date_untouched():
    img = make_image([("Narx: 150 000 so'm", (30, 40), 32, W), ("Sana: 25.10.2026", (30, 140), 32, W)])
    r = clean_image(img)
    assert r.status == "ok" and not r.changed and r.image is img


def test_clean_image_without_text_untouched():
    img = make_image([], bg=(100, 150, 200))
    r = clean_image(img)
    assert r.status == "ok" and not r.changed


def test_commercial_ad_image_rejected():
    img = make_image([("Telefon sotiladi!", (30, 40), 32, W), ("Chegirma 20% gacha", (30, 140), 32, W)])
    r = clean_image(img)
    assert r.status == "reject" and r.reason == "image_commercial_ad"


def test_uncertain_number_goes_to_manual_review():
    img = make_image([("Tel: 123 456 78", (30, 120), 36, W)])
    r = clean_image(img)
    assert r.status == "manual_review" and r.reason == "phone_uncertain_in_image"


def test_huge_overlay_rejected():
    img = make_image([("+998 90 123 45 67", (5, 40), 70, W)], size=(520, 150))
    r = clean_image(img)
    assert r.status == "reject" and r.reason == "too_much_overlay"


class StubbornEngine:
    """Rasmdan qat'i nazar har doim asl raqamni 'ko'radi' (qoplash ishlamayotganini modellashtiradi)."""

    name = "stubborn"

    def read(self, img):
        w = OCRWord("+998", (30, 100, 90, 130)), OCRWord("90", (100, 100, 130, 130)), OCRWord("123", (140, 100, 190, 130)), OCRWord("45", (200, 100, 230, 130)), OCRWord("67", (240, 100, 270, 130))
        return [OCRLine.from_words(list(w))]


def test_cover_that_does_not_remove_number_is_rejected():
    r = clean_image(make_image([("x", (5, 5), 20, W)]), engines=[StubbornEngine()])
    assert r.status == "reject" and r.reason == "cover_failed" and r.image is None


def test_fix_ocr_digits_only_in_numeric_tokens():
    assert fix_ocr_digits("Tel: +99B 9O 123 4S 6l") == "Tel: +998 90 123 45 61"
    assert fix_ocr_digits("Bolsa Sol Obuna") == "Bolsa Sol Obuna"
    assert len(fix_ocr_digits("9O 1l")) == len("9O 1l")


def test_reconcile_drops_uncertain_inside_detected_phone():
    from app.pipeline.media_clean import Flag, reconcile_flags

    flags = [Flag("phone", (10, 10, 200, 40)), Flag("uncertain", (12, 11, 198, 39)), Flag("uncertain", (10, 100, 200, 130))]
    out = reconcile_flags(flags)
    assert [f.kind for f in out] == ["phone", "uncertain"] and out[1].box == (10, 100, 200, 130)
