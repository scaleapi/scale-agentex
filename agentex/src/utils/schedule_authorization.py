from src.api.schemas.authorization_types import (
    AgentexResource,
    AuthorizedOperationType,
)
from src.domain.services.authorization_service import AuthorizationService
from src.utils.visibility_authorization import (
    check_resource_or_collapse_unreadable_to_404,
)


async def _check_schedule_or_collapse_to_404(
    authorization: AuthorizationService,
    schedule_id: str,
    operation: AuthorizedOperationType,
    not_found_message: str | None = None,
) -> None:
    """Check an agent_schedule resource while hiding unreadable schedules.

    ``not_found_message`` overrides the collapsed-404 body. Name-addressed routes
    pass a name-based message so a denied resource is indistinguishable from an
    absent one and the resolved id is never echoed back to an unauthorized caller.
    """
    await check_resource_or_collapse_unreadable_to_404(
        authorization=authorization,
        resource=AgentexResource.schedule(schedule_id),
        operation=operation,
        not_found_message=not_found_message
        or f"Item with id '{schedule_id}' does not exist.",
    )
