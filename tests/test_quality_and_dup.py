import pytest
from pathlib import Path
from PIL import Image, ImageDraw
from app.engines.quality import QualityEngine
from app.engines.duplicate import DuplicateEngine


@pytest.fixture
def sample_image(tmp_path):
    p = tmp_path / "test_img.jpg"
    img = Image.new("RGB", (1920, 1080), color=(50, 100, 150))
    d = ImageDraw.Draw(img)
    d.text((50, 50), "Test Image", fill=(255, 255, 255))
    img.save(p)
    return p


def test_quality_photo_hd(sample_image):
    report = QualityEngine.evaluate_photo(sample_image)
    assert report.is_hd is True
    assert report.width == 1920
    assert report.height == 1080
    assert report.score >= 70


def test_duplicate_sha256(sample_image):
    hash1 = DuplicateEngine.calculate_sha256(sample_image)
    hash2 = DuplicateEngine.calculate_sha256(sample_image)
    assert hash1 == hash2
    assert len(hash1) == 64


def test_duplicate_visual_hashes(sample_image):
    phash, dhash = DuplicateEngine.calculate_visual_hashes(sample_image)
    assert phash is not None
    assert dhash is not None
