from abc import ABC, abstractmethod
from typing import BinaryIO

class StorageProvider(ABC):
    @abstractmethod
    async def save_file(self, filename: str, content: BinaryIO) -> str:
        """
        Save a file and return its unique identifier or path.
        """
        pass

    @abstractmethod
    async def get_file(self, file_id: str) -> bytes:
        """
        Retrieve file content by its identifier.
        """
        pass
