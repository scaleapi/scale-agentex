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
    """Issue a check on an agent resource. On any denial, surface 404 — even
    when the agent exists.

    Mirrors ``check_task_or_collapse_to_404`` (see ``task_authorization.py``).
    The 403/404 split cannot be done safely here: ``AgentORM`` has no tenant
    column, ``agent_repository.get`` does an unfiltered primary-key lookup,
    and ``AuthorizationError`` carries no deny-reason discriminator. Returning
    403 when the row exists and 404 when it doesn't leaks cross-tenant
    existence (caller probes "does agent X exist?" and gets distinguishable
    responses).

    Until agents carry tenant scope (or agentex-auth's deny distinguishes
    "cross-tenant" from "in-tenant lacking permission"), the safer default is
    to collapse both into 404. Trade-off: a user with ``read`` but not
    ``update`` permission on an in-tenant agent sees 404 on update attempts
    instead of 403.

    TODO(AGX1-290): Restore the 403/404 split for same-tenant calls once
    agents carry tenant/account_id scope at the data layer.
    """
    try:
        await authorization.check(
            resource=AgentexResource.agent(agent_id),
            operation=operation,
        )
    except AuthorizationError:
        raise ItemDoesNotExist(f"Item with id '{agent_id}' does not exist.") from None
