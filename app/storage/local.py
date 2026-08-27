import shutil
from pathlib import Path
from typing import Optional
from app.core.config import settings
from app.core.logging import logger
from app.storage.base import StorageProvider


class LocalStorageProvider(StorageProvider):
    """Lokal diskda fayllarni saqlash provayderi."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or settings.STORAGE_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, file_path: Path | str, destination_key: str) -> str:
        src = Path(file_path)
        dest = self.base_dir / destination_key
        dest.parent.mkdir(parents=True, exist_ok=True)

        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        
        return str(destination_key).replace("\\", "/")

    async def get_local_path(self, storage_key: str) -> Path:
        return self.base_dir / storage_key

    async def exists(self, storage_key: str) -> bool:
        return (self.base_dir / storage_key).exists()

    async def delete(self, storage_key: str) -> bool:
        target = self.base_dir / storage_key
        if target.exists():
            try:
                target.unlink()
                return True
            except Exception as e:
                logger.error(f"Faylni o'chirishda xatolik ({storage_key}): {e}")
                return False
        return False
