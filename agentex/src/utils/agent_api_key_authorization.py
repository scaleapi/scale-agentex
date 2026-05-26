from src.adapters.authorization.exceptions import AuthorizationError
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.authorization_types import (
    AgentexResource,
    AuthorizedOperationType,
)


async def _check_api_key_or_collapse_to_404(
    authorization,
    api_key_id: str,
    operation: AuthorizedOperationType,
) -> None:
    """Issue a check on an api_key resource. On any denial, surface 404 — even
    when the api_key exists.

    Same rationale as :func:`src.utils.task_authorization._check_task_or_collapse_to_404`:
    the deny-reason discriminator needed to safely return 403 (in-tenant but
    lacking the operation) vs 404 (cross-tenant or absent) is not available
    here. ``api_key.name`` is unique only per (agent_id, name, api_key_type) —
    not globally — but the existence-leak risk via the name routes is still
    real: a caller probing ``GET /agent_api_keys/name/{name}?agent_id=...``
    against another tenant's agent would otherwise be able to distinguish
    "agent has a key with that name (403)" from "no such key (404)".

    Until api_keys carry tenant scope at the data layer (or agentex-auth's
    deny distinguishes "cross-tenant" from "in-tenant lacking permission"),
    the safer default is to collapse both into 404. Trade-off: a user with
    ``read`` but not ``delete`` permission on an in-tenant api_key sees 404
    on delete attempts instead of 403. UX regression for in-tenant permission
    granularity, but eliminates the cross-tenant existence leak.

    TODO(AGX1-290): Restore the 403/404 split for same-tenant calls once
    api_keys carry tenant/account_id scope at the data layer.
    """
    try:
        await authorization.check(
            resource=AgentexResource.api_key(api_key_id),
            operation=operation,
        )
    except AuthorizationError:
        raise ItemDoesNotExist(f"Item with id '{api_key_id}' does not exist.") from None
