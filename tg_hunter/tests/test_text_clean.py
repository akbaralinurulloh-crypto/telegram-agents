from app.pipeline.text_clean import clean_text


def test_ad_removed_then_phone_replaced():
    r = clean_text("Yangi markaz ochildi.\nAloqa: +998 90 123 45 67\nObuna bo'ling @kanal")
    assert r.status == "ok"
    assert r.text == "Yangi markaz ochildi.\nAloqa: 88 832 77 00"
    assert r.phones_replaced == 1 and r.ads_removed == ["Obuna bo'ling @kanal"]


def test_whatsapp_link_with_number_is_removed_not_half_replaced():
    r = clean_text("Yangilik matni shu yerda.\nWhatsApp wa.me/998901234567")
    assert r.text == "Yangilik matni shu yerda." and r.phones_replaced == 0


def test_commercial_ad_rejected():
    r = clean_text("Telefon sotiladi, chegirma bor! Tel 90 123 45 67")
    assert r.status == "reject" and r.reason == "commercial_ad"


def test_uncertain_number_goes_to_manual_review():
    r = clean_text("Yangilik. Tel: 123 456 78")
    assert r.status == "manual_review" and r.reason == "phone_uncertain" and r.uncertain_numbers


def test_price_and_date_survive():
    r = clean_text("25.10.2026 da narx 1 500 000 so'm bo'ladi")
    assert r.status == "ok" and r.text == "25.10.2026 da narx 1 500 000 so'm bo'ladi"
