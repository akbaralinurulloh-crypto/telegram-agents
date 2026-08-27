import re
from typing import Dict, Any, Tuple
from app.engines.ai_provider import get_ai_provider, MultiCaptionSchema
from app.core.database import get_db_session
from app.models.schema import Caption, ContentCandidate
from app.core.logging import logger


def clean_phone_numbers_and_ads(text: str) -> str:
    """
    Matndan barcha begona telefon raqamlar, murojaat kontaktlari,
    boshqa kompaniyalar reklamalari va havolalarni butunlay tozalaydi.
    """
    if not text:
        return ""

    lines = text.split("\n")
    cleaned_lines = []

    # Kontakt va reklama bilan bog'liq so'zlar
    ad_keywords = [
        "murojaat uchun", "bog'lanish uchun", "boglanish uchun", "aloqa uchun",
        "telefon:", "tel:", "phone:", "call center", "buyurtma berish",
        "admin:", "menejer:", "operator:", "narxi:", "joy band qilish",
        "batafsil ma'lumot", "manzilimiz:", "filialimiz"
    ]

    for line in lines:
        line_lower = line.lower().strip()
        # Agar satr to'liq kontakt/telefon satri bo'lsa tashlab yuboramiz
        if any(kw in line_lower for kw in ad_keywords) and re.search(r"\d{3,}", line):
            continue

        # Har qanday telefon raqam formatini satr ichidan o'chiramiz
        # +998 90 123 45 67, 998901234567, +966..., (99) 123-45-67, 90-123-45-67
        cleaned_line = re.sub(r"(\+?\d{1,3}[\s\-]?)?(\(?\d{2,3}\)?[\s\-]?)?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}", "", line)
        cleaned_line = re.sub(r"\+?\d{9,13}", "", cleaned_line)
        cleaned_line = re.sub(r"t\.me\/(?!muhtashamtraveluzz)[a-zA-Z0-9_+]+", "", cleaned_line) # Begona kanallar linklari

        cleaned_line = cleaned_line.strip()
        if cleaned_line:
            cleaned_lines.append(cleaned_line)

    result = "\n".join(cleaned_lines).strip()
    return result


class CaptionEngine:
    """3 xil uslubda matn generatsiya qiluvchi va saralovchi engine."""

    @classmethod
    async def create_and_store_captions(
        cls,
        candidate_id: int,
        category: str,
        original_caption: str = "",
        analysis_summary: str = ""
    ) -> Tuple[str, str]:
        # 1. Dastlabki matndan barcha telefon raqamlar va reklamalarni tozalash
        clean_orig_caption = clean_phone_numbers_and_ads(original_caption)

        ai = get_ai_provider()
        multi_caps: MultiCaptionSchema = await ai.generate_captions(
            category=category,
            original_caption=clean_orig_caption,
            analysis_summary=analysis_summary
        )

        async with get_db_session() as session:
            # 3 xil uslubni saqlash
            styles_map = {
                "INFORMATIVE": multi_caps.informative,
                "EMOTIONAL": multi_caps.emotional,
                "INTERACTIVE": multi_caps.interactive
            }

            # Kategoriya bo'yicha eng yaxshi uslubni tanlash
            default_selected_style = "EMOTIONAL"
            if category == "Educational":
                default_selected_style = "INFORMATIVE"
            elif category == "Human Story":
                default_selected_style = "INTERACTIVE"

            selected_full_caption = ""

            for style_name, cap_data in styles_map.items():
                is_sel = (style_name == default_selected_style)
                
                # Chiqqan tayyor matndan ham har qanday tasodifiy telefon raqamni tozalash
                clean_full = clean_phone_numbers_and_ads(cap_data.full_caption)

                c_obj = Caption(
                    candidate_id=candidate_id,
                    style=style_name,
                    title=cap_data.title,
                    body=clean_phone_numbers_and_ads(cap_data.body),
                    question=cap_data.question,
                    hashtags=cap_data.hashtags,
                    full_caption=clean_full,
                    is_selected=is_sel
                )
                session.add(c_obj)
                if is_sel:
                    selected_full_caption = clean_full

            await session.commit()
            return default_selected_style, selected_full_caption


caption_engine = CaptionEngine()
