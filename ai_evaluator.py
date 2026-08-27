import os
import json
import asyncio
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from PIL import Image
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL, MIN_QUALITY_SCORE, CHANNEL_TOPIC

logger = logging.getLogger("AIEvaluator")


class EvaluationResult(BaseModel):
    quality_score: int = Field(
        description="1 dan 10 gacha bo'lgan umumiy sifat, tiniqlik va qiziqarlilik bali."
    )
    is_clear: bool = Field(
        description="Rasm yoki video yetarlicha tiniq va sifatlimi?"
    )
    is_interesting: bool = Field(
        description="Kontent odamlar uchun qiziq, tomosha qilishga arziydigan yoki e'tibor tortadimi?"
    )
    is_spam_or_ad: bool = Field(
        description="Bu reklama, spam, kazino/qimor, ortiqcha suvli reklama yoki noo'rin kontentmi?"
    )
    is_approved: bool = Field(
        description="Kanalga joylash uchun tavsiya etiladimi (score >= MIN_SCORE va spam bo'lmasa)?"
    )
    reason: str = Field(
        description="Qabul qilinganligi yoki rad etilganligi haqida qisqa izoh."
    )
    enhanced_caption: str = Field(
        description="Telegram kanali uchun mukammal formatda yozilgan o'zbekcha post matni."
    )


def get_gemini_client() -> genai.Client:
    """Gemini mijozini qaytaradi."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY topilmadi! Iltimos, .env faylida API kalitni kiriting.")
    return genai.Client(api_key=GEMINI_API_KEY)


def build_system_prompt(original_caption: str | None = None) -> str:
    """Tahlil va izoh generatsiya qilish uchun professional prompt."""
    prompt = f"""
Siz professional Telegram kanal muharriri va Sun'iy Intellekt tahlilchisisiz.
Kanal yo'nalishi va mavzusi: "{CHANNEL_TOPIC}".

Vazifalaringiz:
1. MEDIA SIFATINI TAHLIL QILISH:
   - Rasm/video tiniqmi? Xiralashgan yoki sifatsiz emasmi?
   - Kontent odamlarga qiziqmi, tomosha qilishga arziydimi, emotsiya yoki yangi ma'lumot beradimi?
   - Reklama, spam, boshqa kanal havolasi/suv belgisi (watermark), qimor/kazino yoki sifatsiz narsalarni aniqlang.
   - 1 dan 10 gacha baholang (1 - o'ta sifatsiz/zerikarli, 10 - ajoyib/viral).
   - Minimal qabul bali: {MIN_QUALITY_SCORE}. Agar bal >= {MIN_QUALITY_SCORE} va spam bo'lmasa, `is_approved = true` qiling.

2. MUKAMMAL O'ZBEKCHA IZOH (CAPTION) YOZISH:
   Agar `is_approved = true` bo'lsa, Telegram kanali uchun mukammal, jozibador va savodli post matnini tayyorlang:
   - **Sarlavha**: Mavzuga mos emojilar bilan kuchli, diqqat tortuvchi sarlavha (masalan, ⚡️ **Diqqatga sazovor kashfiyot!** yoki 📸 **Ko'rishga arziydigan lahza**).
   - **Asosiy qism**: 2-4 ta tushunarli, ravon va qiziqarli jumlalarda rasm/videodagi holatni yoki uning ma'nosini yoritib bering.
"""
    if original_caption and original_caption.strip():
        prompt += f"""
   - **Mavjud original izoh**: "{original_caption.strip()}"
   - Original izohdagi asosiy foydali ma'lumotni saqlagan holda, uning tilini yanada boyiting, imlo xatolarini to'g'irlang va ancha jozibador qilib qayta yozing.
"""
    else:
        prompt += """
   - Original izoh yo'q, shuning uchun media faylning o'ziga qarab noldan qiziqarli, mazmunli va to'liq izoh yarating.
"""

    prompt += """
   - **Interaktiv yakun**: O'quvchilarni fikr bildirishga yoki do'stlariga ulashishga undovchi 1 ta qisqa savol yoki jumla.
   - **Hashtaglar**: Mavzuga mos 3-4 ta toza hashtag (masalan: `#qiziqarli #dunyo #faktlar`).
   - Formatlash: Telegram Markdown (qalin matn uchun `**so'z**`, kursiv uchun `*so'z*`).

Javobni aniq belgilangan JSON sxemasida qaytaring.
"""
    return prompt


async def evaluate_media(
    media_path: str | Path,
    media_type: str,
    original_caption: str | None = None
) -> EvaluationResult:
    """
    Rasm yoki videoni Gemini orqali tahlil qiladi va izoh tayyorlaydi.
    
    :param media_path: Fayl yo'li (rasm yoki video)
    :param media_type: 'photo' yoki 'video'
    :param original_caption: Dastlabki post izohi (agar bo'lsa)
    """
    media_path = Path(media_path)
    client = get_gemini_client()
    system_prompt = build_system_prompt(original_caption)

    contents = [system_prompt]
    uploaded_file = None

    try:
        if media_type == "photo":
            # Rasmni ochish
            img = Image.open(media_path)
            contents.append(img)
        elif media_type == "video":
            # Videoni Gemini API ga yuklash (asinxron)
            logger.info(f"Video Gemini-ga tahlil uchun yuklanmoqda: {media_path.name}...")
            uploaded_file = await client.aio.files.upload(file=str(media_path))
            # Video qayta ishlanishini kutish
            while getattr(uploaded_file, "state", None) and uploaded_file.state.name == "PROCESSING":
                logger.info("Video Gemini tomonidan qayta ishlanmoqda, kutilmoqda...")
                await asyncio.sleep(2)
                uploaded_file = await client.aio.files.get(name=uploaded_file.name)

            if getattr(uploaded_file, "state", None) and uploaded_file.state.name == "FAILED":
                raise ValueError("Gemini-da videoni qayta ishlash muvaffaqiyatsiz bo'ldi.")

            contents.append(uploaded_file)
        else:
            raise ValueError(f"Noma'lum media turi: {media_type}")

        # AI tahlili (asinxron - retry va fallback modellar bilan)
        logger.info(f"AI media faylni tahlil qilmoqda ({media_type})...")
        models_to_try = [GEMINI_MODEL, "gemini-3.5-flash", "gemini-flash-latest", "gemini-3.7-flash"]
        # Unique tartibda saqlash
        seen = set()
        models_queue = []
        for m in models_to_try:
            if m and m not in seen:
                seen.add(m)
                models_queue.append(m)

        response = None
        last_error = None

        for model_name in models_queue:
            for attempt in range(2):
                try:
                    logger.info(f"Gemini tahlil so'rovi ({model_name}, urinish {attempt + 1})...")
                    response = await client.aio.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=EvaluationResult,
                            temperature=0.4
                        )
                    )
                    if response and response.text:
                        break
                except Exception as e:
                    last_error = e
                    logger.warning(f"Model {model_name} (urinish {attempt + 1}) xatolik: {e}")
                    await asyncio.sleep(2)
            if response and response.text:
                break

        if not response or not response.text:
            raise last_error or RuntimeError("Gemini tahlili muvaffaqiyatsiz bo'ldi.")

        result_data = json.loads(response.text)
        result = EvaluationResult(**result_data)

        logger.info(
            f"Tahlil natijasi: Ball={result.quality_score}/10, "
            f"Tasdiq={result.is_approved}, Sabab='{result.reason}'"
        )
        return result

    finally:
        # Agar video yuklangan bo'lsa, serverdan o'chirish (tozalash)
        if uploaded_file is not None:
            try:
                await client.aio.files.delete(name=uploaded_file.name)
            except Exception as e:
                logger.warning(f"Vaqtinchalik video faylni o'chirishda xatolik: {e}")
