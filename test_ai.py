import os
import sys
import asyncio
from pathlib import Path
from PIL import Image, ImageDraw

# Windows UTF-8 emoji qo'llab-quvvatlash
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


import config
from ai_evaluator import evaluate_media


def create_sample_test_image(path: Path):
    """Test uchun vaqtinchalik sinov rasmini yaratish."""
    img = Image.new('RGB', (800, 600), color=(24, 30, 48))
    d = ImageDraw.Draw(img)
    d.rectangle([(40, 40), (760, 560)], outline=(0, 200, 255), width=4)
    d.text((100, 200), "Sun'iy Intellekt va Koinot Sirlari", fill=(255, 255, 255))
    d.text((100, 260), "Mars sayyorasida yangi suv manbalari aniqlandi!", fill=(200, 220, 255))
    d.text((100, 320), "Olimlar kelajak missiyalari haqida hisobot berishdi.", fill=(180, 180, 180))
    img.save(path)


async def run_test():
    print("==================================================")
    print("🤖 GEMINI AI TAHLIL VA IZOH GENERATORI SINOVI")
    print("==================================================")

    if not config.GEMINI_API_KEY:
        print("❌ XATOLIK: GEMINI_API_KEY .env faylida ko'rsatilmagan!")
        print("Iltimos, '.env' faylini oching va GEMINI_API_KEY qiymatini kiriting.")
        return

    test_img_path = Path(__file__).parent / "downloads" / "test_sample.jpg"
    test_img_path.parent.mkdir(exist_ok=True)
    
    # Agar parametr sifatida rasm berilgan bo'lsa
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        target_path = Path(sys.argv[1])
        media_type = "video" if target_path.suffix.lower() in [".mp4", ".mov", ".avi", ".mkv"] else "photo"
        print(f"📁 Berilgan fayl tekshirilmoqda: {target_path} ({media_type})")
    else:
        create_sample_test_image(test_img_path)
        target_path = test_img_path
        media_type = "photo"
        print(f"🖼 Test namunaviy rasm yaratildi: {target_path}")

    print("\n⏳ Sun'iy intellekt tahlil qilmoqda (Gemini)...")
    try:
        result = await evaluate_media(
            media_path=target_path,
            media_type=media_type,
            original_caption="Marsda suv topildi! Olimlar bu haqida batafsil ma'lumot berdi."
        )

        print("\n---------------- NATIJA ----------------")
        print(f"⭐ Sifat bali: {result.quality_score} / 10")
        print(f"🔍 Tiniqlik: {'Ha' if result.is_clear else 'Yoq'}")
        print(f"🔥 Qiziqarlilik: {'Ha' if result.is_interesting else 'Yoq'}")
        print(f"🚫 Reklama/Spam: {'Ha' if result.is_spam_or_ad else 'Yoq'}")
        print(f"✅ Qabul qilindimi: {'TASDIQLANDI' if result.is_approved else 'RAD ETILDI'}")
        print(f"📝 Izoh/Sabab: {result.reason}")
        print("\n💬 YARATILGAN TELEGRAM POST MATNI:")
        print("========================================")
        print(result.enhanced_caption)
        print("========================================")

    except Exception as e:
        print(f"❌ Xatolik yuz berdi: {e}")
    finally:
        if target_path == test_img_path and test_img_path.exists():
            test_img_path.unlink()


if __name__ == "__main__":
    asyncio.run(run_test())
