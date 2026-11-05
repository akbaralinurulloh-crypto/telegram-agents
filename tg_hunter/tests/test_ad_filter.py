import pytest

from app.pipeline.ad_filter import clean_ads


def test_clean_text_untouched():
    r = clean_ads("Bugun Toshkentda havo ochiq bo'ladi.\nHarorat 25 daraja.")
    assert r.text == "Bugun Toshkentda havo ochiq bo'ladi.\nHarorat 25 daraja." and not r.changed


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Yangilik matni shu yerda.\n\nObuna bo'ling: @mening_kanal", "Yangilik matni shu yerda."),
        ("Yangilik matni shu yerda.\nBizning kanalga qo'shiling t.me/xyz", "Yangilik matni shu yerda."),
        ("Yangilik matni shu yerda.\nBatafsil: https://t.me/xyz/123", "Yangilik matni shu yerda."),
        ("Yangilik matni shu yerda.\n@kanal_nomi", "Yangilik matni shu yerda."),
        ("Yangilik matni shu yerda. Manba: @kanal_nomi", "Yangilik matni shu yerda. Manba"),
        ("@kanal_nomi: yangilik matni shu yerda bo'ladi", "yangilik matni shu yerda bo'ladi"),
        ("Подробности здесь.\nПодписывайтесь на наш канал @news_ru", "Подробности здесь."),
        ("Matn.\nInstagram: instagram.com/abc\nYana matn davomi bor.", "Matn.\nYana matn davomi bor."),
        ("Matn bor shu yerda va yana.\nWhatsApp wa.me/998901234567", "Matn bor shu yerda va yana."),
    ],
)
def test_safe_removal(text, expected):
    r = clean_ads(text)
    assert r.reject_reason is None, r
    assert r.text == expected
    assert r.changed


@pytest.mark.parametrize(
    "text, reason",
    [
        ("Bugun @ali_valiyev bilan uchrashdik va gaplashdik", "inline_link_or_mention"),
        ("Manzil https://example.com/x bo'yicha ro'yxatdan o'ting", "inline_link_or_mention"),
        ("Yangi telefon sotiladi, chegirma 20% gacha!", "commercial_ad"),
        ("Продаю квартиру, скидка до конца недели", "commercial_ad"),
        ("Yangilik matni #reklama", "marked_advertisement"),
        ("Реклама: наш партнёр", "marked_advertisement"),
    ],
)
def test_reject_when_unsafe_or_advertising(text, reason):
    r = clean_ads(text)
    assert r.reject_reason == reason
    assert r.text == text


def test_single_commercial_word_is_not_enough():
    assert clean_ads("Uy narxi oshdi, chegirma kutilmoqda").reject_reason is None


def test_cta_line_removed_even_without_link():
    r = clean_ads("Yangilik matni.\nKanalimizga obuna bo'ling")
    assert r.text == "Yangilik matni." and r.changed


def test_empty():
    assert clean_ads("").text == ""
