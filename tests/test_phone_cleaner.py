import pytest
from app.engines.captioner import clean_phone_numbers_and_ads


def test_clean_phone_numbers_and_ads():
    raw_text = """
    Muborak Umra safari uchun ajoyib imkoniyat!
    Makka va Madina shaharlarida unutilmas ziyorat.
    
    Murojaat uchun: +998 90 123 45 67
    Tel: 998977654321
    Bog'lanish: (99) 111-22-33
    Bizning kanal: t.me/begona_kanal
    """

    cleaned = clean_phone_numbers_and_ads(raw_text)

    # Telefon raqamlar va kontakt satrlari tozalangan bo'lishi kerak
    assert "+998 90 123 45 67" not in cleaned
    assert "998977654321" not in cleaned
    assert "111-22-33" not in cleaned
    assert "Murojaat uchun" not in cleaned
    assert "begona_kanal" not in cleaned

    # Asosiy ma'naviy matn saqlanib qolishi kerak
    assert "Muborak Umra safari uchun ajoyib imkoniyat!" in cleaned
    assert "Makka va Madina shaharlarida unutilmas ziyorat." in cleaned
