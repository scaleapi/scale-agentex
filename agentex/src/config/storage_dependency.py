from functools import lru_cache
from src.adapters.storage.ports import StorageProvider
from src.adapters.storage.local_storage import LocalStorageProvider

@lru_cache()
def get_storage_provider() -> StorageProvider:
    # In a real app, this might read from config to decide whether to use S3 or Local
    return LocalStorageProvider()
