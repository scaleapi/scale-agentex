from src.api.schemas.authorization_types import (
    AgentexResource,
    AuthorizedOperationType,
)
from src.utils.visibility_authorization import (
    check_resource_or_collapse_unreadable_to_404,
)

# Identifier-free 404 detail, reused by the denied-resource branch below and
# by the name routes when the row is absent — keeps both 404s indistinguishable.
API_KEY_NOT_FOUND_MESSAGE = "Agent api_key not found."


async def _check_api_key_or_collapse_to_404(
    authorization,
    api_key_id: str,
    operation: AuthorizedOperationType,
) -> None:
    """Check an api_key resource while hiding unreadable api_keys."""
    await check_resource_or_collapse_unreadable_to_404(
        authorization=authorization,
        resource=AgentexResource.api_key(api_key_id),
        operation=operation,
        not_found_message=API_KEY_NOT_FOUND_MESSAGE,
    )
