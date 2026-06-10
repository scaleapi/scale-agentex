from src.api.schemas.authorization_types import (
    AgentexResource,
    AuthorizedOperationType,
)
from src.domain.services.authorization_service import AuthorizationService
from src.utils.visibility_authorization import (
    check_resource_or_collapse_unreadable_to_404,
)


async def check_task_or_collapse_to_404(
    authorization: AuthorizationService,
    task_id: str,
    operation: AuthorizedOperationType,
) -> None:
    """Check a task resource while hiding unreadable tasks.

    Denied reads collapse to 404. Denied stronger operations preserve 403 when
    the caller can still read the task, and collapse to 404 otherwise.
    """
    await check_resource_or_collapse_unreadable_to_404(
        authorization=authorization,
        resource=AgentexResource.task(task_id),
        operation=operation,
        not_found_message=f"Item with id '{task_id}' does not exist.",
    )
