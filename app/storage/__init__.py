from app.core.config import settings
from app.storage.base import StorageProvider
from app.storage.local import LocalStorageProvider
from app.storage.s3 import S3StorageProvider


def get_storage_provider() -> StorageProvider:
    """Konfiguratsiyaga mos StorageProvider nusxasini qaytaradi."""
    if settings.STORAGE_PROVIDER.lower() == "s3":
        return S3StorageProvider()
    return LocalStorageProvider()
