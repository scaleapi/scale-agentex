from typing import Annotated

from fastapi import Depends, Path, Query, Request

from src.adapters.authorization.exceptions import AuthorizationError
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
    TaskChildResourceType,
)
from src.domain.repositories.agent_repository import DAgentRepository
from src.domain.repositories.agent_task_tracker_repository import (
    DAgentTaskTrackerRepository,
)
from src.domain.repositories.task_message_repository import DTaskMessageRepository
from src.domain.repositories.task_repository import DTaskRepository
from src.domain.repositories.task_state_repository import DTaskStateRepository
from src.domain.services.authorization_service import (
    AuthorizationService,
    DAuthorizationService,
)
from src.utils.agent_api_key_authorization import _check_api_key_or_collapse_to_404
from src.utils.task_authorization import check_task_or_collapse_to_404


async def _get_parent_task_id(
    resource_type: TaskChildResourceType,
    resource_id: str,
    state_repository: DTaskStateRepository,
    message_repository: DTaskMessageRepository,
    tracker_repository: DAgentTaskTrackerRepository,
) -> str:
    """Get the parent task ID for a task-child resource."""
    registry = {
        TaskChildResourceType.state: state_repository,
        TaskChildResourceType.message: message_repository,
        TaskChildResourceType.agent_task_tracker: tracker_repository,
    }

    repository = registry[resource_type]
    resource = await repository.get(id=resource_id)
    return resource.task_id


async def _check_agent_or_collapse_to_404(
    authorization: AuthorizationService,
    agent_id: str,
    operation: AuthorizedOperationType,
) -> None:
    """Check an agent resource; collapse any denial to 404.

    Collapsing a denied check into 404 stops callers from distinguishing 403
    (exists, no access) from 404 (absent) and thereby probing whether an agent
    exists in another tenant. Mirrors the task/api_key collapse helpers.

    TODO: fold this into a single generic collapse helper, and restore the
    403/404 split once agents carry tenant scope at the data layer.
    """
    try:
        await authorization.check(
            resource=AgentexResource.agent(agent_id),
            operation=operation,
        )
    except AuthorizationError:
        raise ItemDoesNotExist(f"Item with id '{agent_id}' does not exist.") from None


def DAuthorizedId(
    resource_type: AgentexResourceType | TaskChildResourceType,
    operation: AuthorizedOperationType = AuthorizedOperationType.read,
    param_name: str = None,
):
    if param_name is None:
        param_name = f"{resource_type.value.lower()}_id"

    async def _ensure_authorized_id(
        authorization: DAuthorizationService,
        state_repository: DTaskStateRepository,
        message_repository: DTaskMessageRepository,
        tracker_repository: DAgentTaskTrackerRepository,
        resource_id: str = Path(..., alias=param_name),
    ) -> str:
        # For child resources, check the parent task. Collapse a denied check
        # into 404 so callers cannot use 403 vs 404 to probe whether a resource
        # exists in another tenant.
        if isinstance(resource_type, TaskChildResourceType):
            task_id = await _get_parent_task_id(
                resource_type,
                resource_id,
                state_repository,
                message_repository,
                tracker_repository,
            )
            await check_task_or_collapse_to_404(authorization, task_id, operation)
        elif resource_type == AgentexResourceType.task:
            await check_task_or_collapse_to_404(authorization, resource_id, operation)
        elif resource_type == AgentexResourceType.api_key:
            # Collapse api_key denials to 404 so name/id probes can't
            # distinguish "present in another tenant" from "absent".
            await _check_api_key_or_collapse_to_404(
                authorization, resource_id, operation
            )
        elif resource_type == AgentexResourceType.agent:
            # Collapse agent denials to 404 for the same discoverability reason.
            await _check_agent_or_collapse_to_404(authorization, resource_id, operation)
        else:
            await authorization.check(
                resource=AgentexResource(type=resource_type, selector=resource_id),
                operation=operation,
            )
        return resource_id

    return Annotated[str, Depends(_ensure_authorized_id)]


def DAuthorizedQuery(
    resource_type: AgentexResourceType | TaskChildResourceType,
    operation: AuthorizedOperationType = AuthorizedOperationType.read,
    param_name: str = None,
    description: str = None,
):
    if param_name is None:
        param_name = f"{resource_type.value.lower()}_id"
    if description is None:
        description = f"The {resource_type.value} ID"

    async def _ensure_authorized_query(
        authorization: DAuthorizationService,
        state_repository: DTaskStateRepository,
        message_repository: DTaskMessageRepository,
        tracker_repository: DAgentTaskTrackerRepository,
        resource_id: str = Query(..., alias=param_name, description=description),
    ) -> str:
        # For child resources, check the parent task. Collapse a denied check
        # into 404 so callers cannot use 403 vs 404 to probe whether a resource
        # exists in another tenant.
        if isinstance(resource_type, TaskChildResourceType):
            task_id = await _get_parent_task_id(
                resource_type,
                resource_id,
                state_repository,
                message_repository,
                tracker_repository,
            )
            await check_task_or_collapse_to_404(authorization, task_id, operation)
        elif resource_type == AgentexResourceType.task:
            await check_task_or_collapse_to_404(authorization, resource_id, operation)
        elif resource_type == AgentexResourceType.agent:
            await _check_agent_or_collapse_to_404(authorization, resource_id, operation)
        else:
            await authorization.check(
                resource=AgentexResource(type=resource_type, selector=resource_id),
                operation=operation,
            )
        return resource_id

    return Annotated[str, Depends(_ensure_authorized_query)]


def DAuthorizedBodyId(
    resource_type: AgentexResourceType,
    operation: AuthorizedOperationType = AuthorizedOperationType.read,
    field_name: str = None,
):
    if field_name is None:
        field_name = f"{resource_type.value}_id"

    async def _ensure_authorized_body_field(
        request: Request,
        authorization: DAuthorizationService,
    ) -> str:
        body = await request.json()
        field_value = body[field_name]

        if resource_type == AgentexResourceType.task:
            await check_task_or_collapse_to_404(authorization, field_value, operation)
        else:
            await authorization.check(
                resource=AgentexResource(type=resource_type, selector=field_value),
                operation=operation,
            )
        return field_value

    return Annotated[str, Depends(_ensure_authorized_body_field)]


def DAuthorizedResourceIds(
    resource_type: AgentexResourceType,
    operation: AuthorizedOperationType = AuthorizedOperationType.read,
):
    async def _list_authorized_resource_ids(
        authorization: DAuthorizationService,
    ) -> list[str] | None:
        maybe_ids_iterable = await authorization.list_resources(
            filter_resource=resource_type,
            filter_operation=operation,
        )
        return list(maybe_ids_iterable) if maybe_ids_iterable is not None else None

    return Annotated[list[str] | None, Depends(_list_authorized_resource_ids)]


def DAuthorizedName(
    resource_type: AgentexResourceType,
    operation: AuthorizedOperationType = AuthorizedOperationType.read,
    param_name: str = None,
):
    if param_name is None:
        param_name = f"{resource_type.value.lower()}_name"

    async def _ensure_authorized_name(
        authorization: DAuthorizationService,
        agent_repository: DAgentRepository,
        task_repository: DTaskRepository,
        resource_name: str = Path(..., alias=param_name),
    ) -> str:
        registry = {
            AgentexResourceType.agent: agent_repository,
            AgentexResourceType.task: task_repository,
        }
        resource_id = resource_name
        repository = registry[resource_type]

        # Lookup-before-authz: if the name isn't present, `repository.get` raises
        # ItemDoesNotExist (→ 404), which is what we want for absent resources.
        # The present-but-denied case is handled per-resource below.
        resource = await repository.get(name=resource_id)

        if resource_type == AgentexResourceType.task:
            # Tasks: collapse denial to 404 so name probes can't distinguish
            # "present in another tenant" from "absent" (tasks.name is globally
            # unique — any 403 leak here probes the whole system, not a tenant).
            await check_task_or_collapse_to_404(authorization, resource.id, operation)
        elif resource_type == AgentexResourceType.agent:
            # Agents: same collapse, on the id resolved from the name above.
            await _check_agent_or_collapse_to_404(authorization, resource.id, operation)
        else:
            await authorization.check(
                resource=AgentexResource(type=resource_type, selector=resource.id),
                operation=operation,
            )
        return resource_id

    return Annotated[str, Depends(_ensure_authorized_name)]
