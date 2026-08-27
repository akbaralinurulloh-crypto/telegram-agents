import pytest
from app.engines.target_auditor import TargetChannelAuditor


def test_target_auditor_detection():
    auditor = TargetChannelAuditor()
    auditor.known_captions = ["umra ziyoratidagi qulayliklar va mazali taomlar 14 kunlik ziyorat"]
    auditor.known_file_sizes.add(1048576) # 1 MB
    auditor.known_durations.add(55.2)

    # 1. Caption similarity test
    is_dup, reason = auditor.is_content_already_posted(caption="Umra ziyoratidagi qulayliklar va mazali taomlar! 14 kunlik Umra safari")
    assert is_dup is True
    assert "Kanalda mavjud" in reason

    # 2. File size test
    is_dup_size, _ = auditor.is_content_already_posted(file_size=1048576)
    assert is_dup_size is True

    # 3. New content test
    is_dup_new, _ = auditor.is_content_already_posted(caption="Butunlay yangi va boshqa mavzudagi post", file_size=500000)
    assert is_dup_new is False
