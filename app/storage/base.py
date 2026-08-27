from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class StorageProvider(ABC):
    """Media fayllarni saqlash provayderi uchun abstrakt interfeys."""

    @abstractmethod
    async def save(self, file_path: Path | str, destination_key: str) -> str:
        """Faylni storage omboriga nusxalaydi/yuklaydi va storage_key qaytaradi."""
        pass

    @abstractmethod
    async def get_local_path(self, storage_key: str) -> Path:
        """Faylning lokal diskdagi yo'lini qaytaradi (zarur bo'lsa keshdan yuklab oladi)."""
        pass

    @abstractmethod
    async def exists(self, storage_key: str) -> bool:
        """Fayl mavjudligini tekshiradi."""
        pass

    @abstractmethod
    async def delete(self, storage_key: str) -> bool:
        """Faylni storage omboridan o'chiradi."""
        pass
