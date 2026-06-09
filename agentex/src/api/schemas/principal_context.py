from types import SimpleNamespace
from typing import Any

AgentexAuthPrincipalContext = Any


def _is_api_key_field_name(field_name: Any) -> bool:
    if not isinstance(field_name, str):
        return False
    return field_name.replace("_", "").replace("-", "").lower() == "apikey"


def remove_api_key_from_principal_context(
    principal_context: AgentexAuthPrincipalContext,
) -> AgentexAuthPrincipalContext:
    """Return a principal context with API-key secret fields removed."""
    if isinstance(principal_context, dict):
        return {
            key: remove_api_key_from_principal_context(value)
            for key, value in principal_context.items()
            if not _is_api_key_field_name(key)
        }

    if isinstance(principal_context, list):
        return [
            remove_api_key_from_principal_context(value) for value in principal_context
        ]

    if isinstance(principal_context, tuple):
        return tuple(
            remove_api_key_from_principal_context(value) for value in principal_context
        )

    model_dump = getattr(principal_context, "model_dump", None)
    if callable(model_dump):
        return remove_api_key_from_principal_context(model_dump())

    if hasattr(principal_context, "__dict__"):
        return SimpleNamespace(
            **{
                key: remove_api_key_from_principal_context(value)
                for key, value in vars(principal_context).items()
                if not key.startswith("_") and not _is_api_key_field_name(key)
            }
        )

    return principal_context
