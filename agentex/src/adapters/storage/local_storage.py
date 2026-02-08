import os
import shutil
from pathlib import Path
from typing import BinaryIO
import uuid

from src.adapters.storage.ports import StorageProvider

    """
    Implementation of StorageProvider that saves files to the local filesystem.
    This is suitable for development or single-instance deployments.
    """
    def __init__(self, upload_dir: str = "uploads"):
        """
        Initialize the local storage provider.
        
        Args:
            upload_dir: Directory path where files will be stored. Defaults to "uploads".
        """
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def save_file(self, filename: str, content: BinaryIO) -> str:
        """
        Save a file to the local disk.
        
        Args:
            filename: Original name of the file.
            content: Binary file content.
            
        Returns:
            str: The unique file ID (path relative to upload_dir).
        """
        # Generate a unique ID for the file to prevent collisions
        file_id = f"{uuid.uuid4()}_{filename}"
        file_path = self.upload_dir / file_id
        
        # Use run_in_threadpool to perform blocking I/O in a separate thread
        # This prevents blocking the main event loop
        from starlette.concurrency import run_in_threadpool
        
        def _save():
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(content, buffer)
                
        await run_in_threadpool(_save)
            
        return file_id

    async def get_file(self, file_id: str) -> bytes:
        file_path = self.upload_dir / file_id
        if not file_path.exists():
            raise FileNotFoundError(f"File {file_id} not found")
            
        with open(file_path, "rb") as f:
            return f.read()
