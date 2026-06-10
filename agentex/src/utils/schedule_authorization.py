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
) -> None:
    """Check an agent_schedule resource while hiding unreadable schedules."""
    await check_resource_or_collapse_unreadable_to_404(
        authorization=authorization,
        resource=AgentexResource.schedule(schedule_id),
        operation=operation,
        not_found_message=f"Item with id '{schedule_id}' does not exist.",
    )
