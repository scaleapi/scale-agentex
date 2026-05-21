"""
Cursor-based pagination utilities.

Provides encode/decode functions for creating opaque cursor strings
that can be used for stable pagination through result sets.
"""

import base64
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from src.utils.logging import make_logger

logger = make_logger(__name__)


class CursorData(BaseModel):
    """Internal cursor structure - versioned for future compatibility."""

    v: int = 1  # Version for backwards compatibility
    id: str  # Document ID
    created_at: str  # ISO format timestamp


def encode_cursor(id: str, created_at: datetime | None) -> str | None:
    """
    Encode pagination position into an opaque cursor string.

    Args:
        id: The document ID
        created_at: The document's creation timestamp

    Returns:
        Base64-encoded cursor string, or None if created_at is null

    Note:
        Returns None if created_at is null since cursors require timestamps
        for stable pagination ordering.
    """
    if created_at is None:
        return None

    cursor_data = CursorData(
        id=id,
        created_at=created_at.isoformat(),
    )
    json_str = cursor_data.model_dump_json()
    return base64.urlsafe_b64encode(json_str.encode()).decode()


def decode_cursor(cursor: str) -> CursorData:
    """
    Decode cursor string back to pagination data.

    Args:
        cursor: Base64-encoded cursor string

    Returns:
        CursorData with id and created_at

    Raises:
        ValueError: If cursor format is invalid
    """
    try:
        json_str = base64.urlsafe_b64decode(cursor.encode()).decode()
        return CursorData.model_validate_json(json_str)
    except Exception as e:
        raise ValueError(f"Invalid cursor format: {e}") from e


class PaginatedResponse(BaseModel):
    """Response wrapper with cursor pagination metadata."""

    data: list[Any]
    next_cursor: str | None = None
    has_more: bool = False
