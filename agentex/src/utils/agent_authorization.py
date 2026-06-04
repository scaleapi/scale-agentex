from src.adapters.authorization.exceptions import AuthorizationError
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.authorization_types import (
    AgentexResource,
    AuthorizedOperationType,
)


async def check_agent_or_collapse_to_404(
    authorization,
    agent_id: str,
    operation: AuthorizedOperationType,
) -> None:
    """Check an agent resource; collapse any denial to 404 to avoid leaking
    cross-tenant existence. Mirrors ``check_task_or_collapse_to_404`` in
    ``task_authorization.py`` — see that docstring for the full rationale.

    TODO: Restore the 403/404 split once agents carry tenant scope.
    """
    try:
        await authorization.check(
            resource=AgentexResource.agent(agent_id),
            operation=operation,
        )
    except AuthorizationError:
        raise ItemDoesNotExist(f"Item with id '{agent_id}' does not exist.") from None
