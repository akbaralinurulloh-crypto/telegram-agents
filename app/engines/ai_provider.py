import json
import asyncio
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from PIL import Image
from google import genai
from google.genai import types

from app.core.config import settings
from app.core.logging import logger
from app.core.database import get_db_session
from app.models.schema import AICost


class AnalysisSchema(BaseModel):
    category: str = Field(default="General", description="Kontent toifasi (Makkah, Madinah, Spiritual, Educational, Human Story)")
    sub_category: str = Field(default="", description="Qo'shimcha tor mavzu")
    tags: List[str] = Field(default_factory=list, description="3-5 ta asosiy kalit so'z")
    visual_quality: int = Field(default=70, description="0-100 visual quality score")
    emotional_impact: int = Field(default=70, description="0-100 emotional impact score")
    relevance: int = Field(default=70, description="0-100 topic relevance score")
    uniqueness: int = Field(default=70, description="0-100 uniqueness score")
    freshness: int = Field(default=70, description="0-100 freshness score")
    information_value: int = Field(default=70, description="0-100 educational/spiritual value score")
    risk_level: str = Field(default="LOW", description="LOW, MEDIUM, HIGH")
    confidence: float = Field(default=0.85, description="0.0 - 1.0 confidence")
    recommendation: str = Field(default="CANDIDATE", description="CANDIDATE, REJECT, REVIEW")
    reason: str = Field(default="", description="Qaror izohi")


class CaptionStyleSchema(BaseModel):
    title: str = Field(default="")
    body: str = Field(default="")
    question: str = Field(default="")
    hashtags: str = Field(default="")
    full_caption: str = Field(default="")


class MultiCaptionSchema(BaseModel):
    informative: CaptionStyleSchema
    emotional: CaptionStyleSchema
    interactive: CaptionStyleSchema


class AIProvider(ABC):
    @abstractmethod
    async def analyze_media(self, media_path: Path, media_type: str, original_caption: str = "") -> AnalysisSchema:
        pass

    @abstractmethod
    async def generate_captions(self, category: str, original_caption: str = "", analysis_summary: str = "") -> MultiCaptionSchema:
        pass


class GeminiAIProvider(AIProvider):
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        if not self.api_key:
            logger.warning("GEMINI_API_KEY sozlanmagan!")

    def _get_client(self) -> genai.Client:
        return genai.Client(api_key=self.api_key)

    def _load_prompt(self, filename: str) -> str:
        prompt_path = settings.BASE_DIR / "app" / "prompts" / filename
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return ""

    async def _track_cost(self, model: str, request_type: str, latency_ms: int, prompt_tokens: int = 500, completion_tokens: int = 300):
        # Narx hisoblash (o'rtacha $0.075 / 1M token flash uchun)
        est_cost = (prompt_tokens * 0.075 + completion_tokens * 0.3) / 1_000_000
        try:
            async with get_db_session() as session:
                session.add(AICost(
                    model_name=model,
                    request_type=request_type,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    estimated_cost_usd=est_cost,
                    latency_ms=latency_ms
                ))
                await session.commit()
        except Exception:
            pass

    async def analyze_media(self, media_path: Path, media_type: str, original_caption: str = "") -> AnalysisSchema:
        client = self._get_client()
        base_prompt = self._load_prompt("analyzer.txt").format(channel_topic=settings.CHANNEL_TOPIC)
        safety_prompt = self._load_prompt("safety.txt")
        full_system_prompt = f"{base_prompt}\n\n{safety_prompt}\n\nDastlabki matn: '{original_caption}'"

        contents = [full_system_prompt]
        uploaded_file = None

        t0 = time.time()
        try:
            if media_type == "photo" or media_path.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                img = Image.open(media_path)
                contents.append(img)
            elif media_type in ["video", "video_note"] or media_path.suffix.lower() in [".mp4", ".mov", ".mkv", ".avi"]:
                logger.info(f"Video tahlil uchun Gemini serveriga yuklanmoqda: {media_path.name}")
                uploaded_file = await client.aio.files.upload(file=str(media_path))
                while getattr(uploaded_file, "state", None) and uploaded_file.state.name == "PROCESSING":
                    await asyncio.sleep(2)
                    uploaded_file = await client.aio.files.get(name=uploaded_file.name)
                
                if getattr(uploaded_file, "state", None) and uploaded_file.state.name == "FAILED":
                    raise ValueError("Gemini videoni qayta ishlay olmadi.")
                contents.append(uploaded_file)

            models_to_try = [settings.GEMINI_MODEL] + settings.FALLBACK_MODELS
            # Unique tartibda
            seen = set()
            clean_models = [m for m in models_to_try if m and not (m in seen or seen.add(m))]

            response = None
            last_err = None
            used_model = clean_models[0]

            for model_name in clean_models:
                try:
                    logger.debug(f"Gemini Vision so'rovi: {model_name}...")
                    response = await client.aio.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=AnalysisSchema,
                            temperature=0.3
                        )
                    )
                    if response and response.text:
                        used_model = model_name
                        break
                except Exception as e:
                    last_err = e
                    logger.warning(f"Model {model_name} xatosi: {e}")
                    await asyncio.sleep(1)

            if not response or not response.text:
                raise last_err or RuntimeError("Gemini tahlili amalga oshmadi.")

            latency = int((time.time() - t0) * 1000)
            asyncio.create_task(self._track_cost(used_model, "ANALYSIS", latency))

            data = json.loads(response.text)
            return AnalysisSchema(**data)

        finally:
            if uploaded_file is not None:
                try:
                    await client.aio.files.delete(name=uploaded_file.name)
                except Exception:
                    pass

    async def generate_captions(self, category: str, original_caption: str = "", analysis_summary: str = "") -> MultiCaptionSchema:
        client = self._get_client()
        base_prompt = self._load_prompt("caption.txt").format(
            channel_topic=settings.CHANNEL_TOPIC,
            category=category,
            original_caption=original_caption
        )
        safety_prompt = self._load_prompt("safety.txt")
        full_prompt = f"{base_prompt}\n\n{safety_prompt}\n\nMedia tahlili xulosasi: {analysis_summary}"

        t0 = time.time()
        models_to_try = [settings.GEMINI_MODEL] + settings.FALLBACK_MODELS
        seen = set()
        clean_models = [m for m in models_to_try if m and not (m in seen or seen.add(m))]

        response = None
        last_err = None
        used_model = clean_models[0]

        for model_name in clean_models:
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=MultiCaptionSchema,
                        temperature=0.6
                    )
                )
                if response and response.text:
                    used_model = model_name
                    break
            except Exception as e:
                last_err = e
                logger.warning(f"Caption generatsiya model {model_name} xatosi: {e}")
                await asyncio.sleep(1)

        latency = int((time.time() - t0) * 1000)
        asyncio.create_task(self._track_cost(used_model, "CAPTION", latency))

        if response and response.text:
            try:
                data = json.loads(response.text)
                return MultiCaptionSchema(**data)
            except Exception as e:
                logger.warning(f"AI Caption JSON parse xatosi: {e}")

        # Fallback agar AI ishlamay qolsa
        base_clean = original_caption[:200] if original_caption else "Alloh taolo barchamizga muqaddas ziyoratlarni nasib aylasin."
        default_style = CaptionStyleSchema(
            title="✨ Muhtasham Ziyorat",
            body=base_clean,
            question="Siz ham ushbu muqaddas maskanlarni ziyorat qilishni niyat qilganmisiz?",
            hashtags="#Umra #Madina #Makka #Ziyorat",
            full_caption=f"✨ **Muhtasham Ziyorat**\n\n{base_clean}\n\n🕌 @muhtashamtraveluzz\n#Umra #Madina #Makka"
        )
        return MultiCaptionSchema(informative=default_style, emotional=default_style, interactive=default_style)


def get_ai_provider() -> AIProvider:
    return GeminiAIProvider()
