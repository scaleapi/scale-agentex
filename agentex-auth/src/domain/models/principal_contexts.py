from typing import Any

from pydantic import BaseModel


class SGPPrincipalContext(BaseModel):
    api_key: str | None = None
    user_id: str | None = None
    account_id: str | None = None
    raw_user: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
