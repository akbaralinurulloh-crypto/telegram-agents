import pytest

from app.pipeline.phone_replace import REPLACEMENT, replace_phones

PHONES = [
    "+998 90 123 45 67",
    "+998901234567",
    "998901234567",
    "998 90 123 45 67",
    "90 123 45 67",
    "90-123-45-67",
    "90.123.45.67",
    "(90) 123 45 67",
    "(90)123-45-67",
    "+998(90)1234567",
    "+998 (90) 123-45-67",
    "+998-90-123-45-67",
    "+998.90.123.45.67",
    "901234567",
    "90 1234567",
    "901 234 567",
    "8 90 123 45 67",
    "0 90 123 45 67",
    "+99890 123 45 67",
    "+998 33 456 78 90",
    "+998 97 765 43 21",
    "+998 71 234 56 78",
    "+998  90  123  45  67",
    "+998 90 123 45 67",
    "+998 90 123-45-67",
    "90 123 4567",
    "+7 495 123 45 67",
    "+7 (495) 123-45-67",
    "8 (495) 123-45-67",
    "+1 (212) 555-0123",
    "+44 20 7946 0958",
    "9️⃣0️⃣ 1️⃣2️⃣3️⃣ 4️⃣5️⃣ 6️⃣7️⃣",
    "+998 90 123•45•67",
    "+998 90 123x45x67",
    "٩٠ ١٢٣ ٤٥ ٦٧",
    "９０ １２３ ４５ ６７",
    "+998 90 1️⃣23 45 67",
    "+998_90_123_45_67",
]


@pytest.mark.parametrize("phone", PHONES)
def test_phone_format_replaced(phone):
    r = replace_phones(f"Aloqa: {phone} ga yozing")
    assert r.text == f"Aloqa: {REPLACEMENT} ga yozing", r
    assert r.replaced == 1
    assert r.uncertain == []


def test_at_least_30_formats_covered():
    assert len(PHONES) >= 30


def test_multiple_numbers_and_surrounding_text_kept():
    r = replace_phones("Ali: 90 123 45 67\nVali: +998 91 765 43 21 (WhatsApp)")
    assert r.text == f"Ali: {REPLACEMENT}\nVali: {REPLACEMENT} (WhatsApp)"
    assert r.replaced == 2


def test_target_number_untouched_and_not_counted():
    r = replace_phones("Tel: 88 832 77 00")
    assert r.text == "Tel: 88 832 77 00" and r.replaced == 0 and r.uncertain == []


@pytest.mark.parametrize(
    "text",
    [
        "Narx: 150 000 so'm",
        "Narx 1 500 000 so'm",
        "Narx: 905 000 000 so'm",
        "Narx: 905 000 000",
        "1,500,000 UZS",
        "Sana: 25.10.2026",
        "25.10.2026 14:30 da",
        "2026-10-25",
        "ID: 901234567",
        "Buyurtma № 901234567",
        "Kod 990123456",
        "Yil 2024, 2025 va 2026",
        "12 ta 3 kg 450 ml",
        "Reyting 4.8 / 5",
        "98% foydalanuvchi, 1200 ta",
        "192.168.1.100 manzil",
        "Karta: 8600 1234 5678 9012",
        "50 000 000 dollar",
        "3 000 000 so'm",
    ],
)
def test_non_phones_untouched(text):
    r = replace_phones(text)
    assert r.text == text, r
    assert r.replaced == 0
    assert r.uncertain == [], r


def test_suspicious_number_near_keyword_is_flagged_not_replaced():
    r = replace_phones("Tel: 123 456 78")
    assert r.text == "Tel: 123 456 78"
    assert r.uncertain


def test_long_unknown_digit_stream_is_flagged():
    r = replace_phones("Raqam 4455 6677 8899 haqida")
    assert r.uncertain


def test_empty():
    assert replace_phones("").text == ""


def test_emoji_next_to_number_is_kept():
    assert replace_phones("📞 +998 90 123 45 67📞").text == f"📞 {REPLACEMENT}📞"
