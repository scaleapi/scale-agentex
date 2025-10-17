from typing import Any

from jsonschema import ValidationError
from jsonschema import validate as schema_validation

from src.domain.exceptions import ClientError


class JSONSchemaValidationError(ClientError):
    """
    Error raised when there is an issue with the JSON schema validation.
    """

    code = 400


def validate_payload(json_schema: dict[str, Any], payload: dict[str, Any]) -> None:
    """Validate the payload against the JSON schema."""
    try:
        schema_validation(instance=payload, schema=json_schema)
    except ValidationError as e:
        raise JSONSchemaValidationError(f"Payload validation error: {e.message}") from e
