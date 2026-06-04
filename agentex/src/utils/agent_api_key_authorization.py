from src.adapters.authorization.exceptions import AuthorizationError
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.authorization_types import (
    AgentexResource,
    AuthorizedOperationType,
)

# Identifier-free 404 detail, reused by the denied-resource branch below and
# by the name routes when the row is absent — keeps both 404s indistinguishable.
API_KEY_NOT_FOUND_MESSAGE = "Agent api_key not found."


async def _check_api_key_or_collapse_to_404(
    authorization,
    api_key_id: str,
    operation: AuthorizedOperationType,
) -> None:
    """Check an api_key resource; collapse any denial to 404 to avoid leaking
    cross-tenant existence. Mirrors ``_check_task_or_collapse_to_404``.

    TODO: Restore the 403/404 split once api_keys carry tenant scope.
    """
    try:
        await authorization.check(
            resource=AgentexResource.api_key(api_key_id),
            operation=operation,
        )
    except AuthorizationError:
        raise ItemDoesNotExist(API_KEY_NOT_FOUND_MESSAGE) from None
