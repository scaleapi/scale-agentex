from src.adapters.authorization.exceptions import AuthorizationError
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.authorization_types import (
    AgentexResource,
    AuthorizedOperationType,
)
from src.domain.services.authorization_service import AuthorizationService


async def _check_schedule_or_collapse_to_404(
    authorization: AuthorizationService,
    schedule_id: str,
    operation: AuthorizedOperationType,
) -> None:
    """Issue a check on an agent_schedule resource. On any denial, surface 404 —
    even when the schedule exists.

    Same rationale as the task / api_key equivalents: the deny-reason
    discriminator needed to safely return 403 (in-tenant but lacking the
    operation) vs 404 (cross-tenant or absent) is not available here. Schedules
    have no Postgres row and no tenant column — Temporal is the store and the
    selector is ``{agent_id}--{schedule_name}`` — so a 403/404 split would let a
    caller who can resolve an ``agent_id`` probe another tenant's schedule names
    by comparing "exists but denied (403)" against "absent (404)".

    Because the single-resource routes run this check *before* the Temporal
    lookup, a denied schedule and an absent schedule both exit here with the
    same generic body, so the two cases are indistinguishable under enforcement.

    Until schedules carry tenant scope at the data layer (or the authorization
    service's deny distinguishes "cross-tenant" from "in-tenant lacking
    permission"), the safer default is to collapse both into 404. Trade-off: a
    user with ``read`` but not ``update`` permission on an in-tenant schedule
    sees 404 on pause/trigger/delete attempts instead of 403. UX regression for
    in-tenant permission granularity, but eliminates the cross-tenant existence
    leak.

    TODO: Restore the 403/404 split for same-tenant calls once schedules carry
    tenant/account_id scope at the data layer.
    """
    try:
        await authorization.check(
            resource=AgentexResource.schedule(schedule_id),
            operation=operation,
        )
    except AuthorizationError:
        raise ItemDoesNotExist(
            f"Item with id '{schedule_id}' does not exist."
        ) from None
