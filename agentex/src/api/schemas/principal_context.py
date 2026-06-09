from collections.abc import Mapping
from typing import Any

from pydantic import ConfigDict, model_validator

from src.utils.model_utils import BaseModel


def _is_api_key_field_name(field_name: Any) -> bool:
    if not isinstance(field_name, str):
        return False
    return field_name.replace("_", "").replace("-", "").lower() == "apikey"


class AgentexAuthPrincipalContext(BaseModel):
    """Principal context passed through Agentex authz.

    The authn service can return the credential used to authenticate the caller,
    but Agentex only needs the resolved principal identifiers. Keep the API key
    out of the base object entirely so it cannot be logged or forwarded through
    authz payloads.
    """

    model_config = ConfigDict(
        extra="allow",
        from_attributes=True,
        populate_by_name=True,
    )

    user_id: str | None = None
    service_account_id: str | None = None
    account_id: str | None = None
    agent_id: str | None = None
    id: str | None = None
    sub: str | None = None
    email: str | None = None

    @model_validator(mode="before")
    @classmethod
    def remove_api_key(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            return {
                key: value
                for key, value in data.items()
                if not _is_api_key_field_name(key)
            }

        if hasattr(data, "__dict__"):
            return {
                key: value
                for key, value in vars(data).items()
                if not key.startswith("_") and not _is_api_key_field_name(key)
            }

        return data
