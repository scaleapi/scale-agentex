from src.adapters.authorization.exceptions import AuthorizationError
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.authorization_types import (
    AgentexResource,
    AuthorizedOperationType,
)
from src.domain.services.authorization_service import AuthorizationService


async def check_task_or_collapse_to_404(
    authorization: AuthorizationService,
    task_id: str,
    operation: AuthorizedOperationType,
) -> None:
    """Issue a check on a task resource. On any denial, surface 404 — even when
    the task exists.

    The 403/404 split cannot be done safely here: ``TaskORM`` has no tenant
    column, ``task_repository.get`` does an unfiltered primary-key lookup, and
    ``AuthorizationError`` carries no deny-reason discriminator. Returning 403
    when the row exists and 404 when it doesn't leaks cross-tenant existence
    (caller probes "does task X exist?" and gets distinguishable responses).

    Until tasks carry tenant scope (or agentex-auth's deny distinguishes
    "cross-tenant" from "in-tenant lacking permission"), the safer default is
    to collapse both into 404. Trade-off: a user with ``read`` but not
    ``update`` permission on an in-tenant task sees 404 on update attempts
    instead of 403. UX regression for in-tenant permission granularity, but
    eliminates the cross-tenant existence leak.

    TODO: Restore the 403/404 split once tasks carry tenant scope at the
    data layer (task rows currently have no tenant column).
    """
    try:
        await authorization.check(
            resource=AgentexResource.task(task_id),
            operation=operation,
        )
    except AuthorizationError:
        raise ItemDoesNotExist(f"Item with id '{task_id}' does not exist.") from None
