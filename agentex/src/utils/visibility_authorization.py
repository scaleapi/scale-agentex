from src.adapters.authorization.exceptions import AuthorizationError
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.authorization_types import (
    AgentexResource,
    AuthorizedOperationType,
)
from src.domain.services.authorization_service import AuthorizationService


async def check_resource_or_collapse_unreadable_to_404(
    authorization: AuthorizationService,
    resource: AgentexResource,
    operation: AuthorizedOperationType,
    not_found_message: str,
) -> None:
    """Check a resource while hiding only resources the caller cannot read.

    If the requested operation is denied, a denied ``read`` check still
    collapses to 404 to avoid resource-existence probing. For stronger
    operations, a successful follow-up ``read`` check means the caller can
    already see the resource, so the original authorization denial is preserved
    as 403. If ``read`` is also denied, the response stays 404.
    """
    try:
        await authorization.check(resource=resource, operation=operation)
    except AuthorizationError as exc:
        if operation != AuthorizedOperationType.read:
            try:
                await authorization.check(
                    resource=resource,
                    operation=AuthorizedOperationType.read,
                )
            except AuthorizationError:
                pass
            else:
                raise exc
        raise ItemDoesNotExist(not_found_message) from None
