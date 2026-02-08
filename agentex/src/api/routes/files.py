from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from src.adapters.storage.ports import StorageProvider
from src.config.storage_dependency import get_storage_provider
from src.domain.entities.task_messages import FileAttachmentEntity

router = APIRouter(prefix="/files", tags=["Files"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIME_TYPES = {
    "text/plain",
    "text/csv", 
    "text/markdown",
    "application/json",
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif"
}

@router.post(
    "/upload",
    response_model=FileAttachmentEntity,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    file: UploadFile,
    storage_provider: Annotated[StorageProvider, Depends(get_storage_provider)],
) -> FileAttachmentEntity:
    """
    Upload a file to be attached to a message.
    """
    # 1. Validation
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {file.content_type} not allowed. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
        )
    
    # We need to check file size. UploadFile is a SpooledTemporaryFile.
    # We can check size by seeking to end, but that might be expensive for large files if not already spooled to disk?
    # Given the 10MB limit and modern FastAPI behavior (spools to disk after limit), likely safe to just read/check length or check headers if trusted (headers not trusted).
    # Safer to count bytes while reading or just seek. 
    # Use file.size if available (populated by python-multipart), otherwise read
    if file.size is not None:
        file_size = file.size
    else:
        await file.seek(0)
        content = await file.read()
        file_size = len(content)
        await file.seek(0)

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum limit of {MAX_FILE_SIZE / (1024*1024)}MB"
        )
        
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty"
        )

    # 2. Save File
    try:
        file_id = await storage_provider.save_file(file.filename or "unknown", file.file)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )

    # 3. Return Entity
    return FileAttachmentEntity(
        file_id=file_id,
        name=file.filename or "unknown",
        size=file_size,
        type=file.content_type or "application/octet-stream"
    )
