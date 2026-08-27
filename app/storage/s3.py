from pathlib import Path
from typing import Optional
from app.core.config import settings
from app.core.logging import logger
from app.storage.base import StorageProvider
from app.storage.local import LocalStorageProvider


class S3StorageProvider(StorageProvider):
    """S3/Cloudflare R2/MinIO bulutli ombor provayderi (Local kesh zaxirasi bilan)."""

    def __init__(self):
        self.fallback = LocalStorageProvider()
        self.bucket = settings.S3_BUCKET_NAME
        self.endpoint = settings.S3_ENDPOINT

    async def save(self, file_path: Path | str, destination_key: str) -> str:
        # S3 sozlanmagan bo'lsa lokal provayderga xavfsiz yo'naltirish
        if not settings.S3_ACCESS_KEY or not settings.S3_SECRET_KEY:
            return await self.fallback.save(file_path, destination_key)

        try:
            # Agar aioboto3 o'rnatilgan bo'lsa S3 ga yuklash
            import aioboto3 # type: ignore
            session = aioboto3.Session()
            async with session.client(
                "s3",
                endpoint_url=self.endpoint or None,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY
            ) as s3:
                with open(file_path, "rb") as f:
                    await s3.upload_fileobj(f, self.bucket, destination_key)
            return destination_key
        except Exception as e:
            logger.warning(f"S3 yuklashda xatolik yuz berdi, lokal diskka saqlanmoqda: {e}")
            return await self.fallback.save(file_path, destination_key)

    async def get_local_path(self, storage_key: str) -> Path:
        return await self.fallback.get_local_path(storage_key)

    async def exists(self, storage_key: str) -> bool:
        return await self.fallback.exists(storage_key)

    async def delete(self, storage_key: str) -> bool:
        return await self.fallback.delete(storage_key)
