from typing import Annotated

from fastapi import Depends, Path, Query, Request

from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
    TaskChildResourceType,
)
from src.domain.repositories.agent_repository import DAgentRepository
from src.domain.repositories.event_repository import DEventRepository
from src.domain.repositories.task_repository import DTaskRepository
from src.domain.repositories.task_state_repository import DTaskStateRepository
from src.domain.services.authorization_service import DAuthorizationService


async def _get_parent_task_id(
    resource_type: TaskChildResourceType,
    resource_id: str,
    event_repository: DEventRepository,
    state_repository: DTaskStateRepository,
) -> str:
    """Get the parent task ID for a child resource."""
    registry = {
        TaskChildResourceType.state: state_repository,
        TaskChildResourceType.event: event_repository,
    }

    repository = registry[resource_type]
    resource = await repository.get(id=resource_id)
    return resource.task_id


def DAuthorizedId(
    resource_type: AgentexResourceType | TaskChildResourceType,
    operation: AuthorizedOperationType = AuthorizedOperationType.read,
    param_name: str = None,
):
    if param_name is None:
        param_name = f"{resource_type.value.lower()}_id"

    async def _ensure_authorized_id(
        authorization: DAuthorizationService,
        event_repository: DEventRepository,
        state_repository: DTaskStateRepository,
        resource_id: str = Path(..., alias=param_name),
    ) -> str:
        # For child resources, check the parent task
        if isinstance(resource_type, TaskChildResourceType):
            task_id = await _get_parent_task_id(
                resource_type, resource_id, event_repository, state_repository
            )
            await authorization.check(
                resource=AgentexResource.task(task_id),
                operation=operation,
            )
        else:
            # For direct resources, check directly
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
        event_repository: DEventRepository,
        state_repository: DTaskStateRepository,
        resource_id: str = Query(..., alias=param_name, description=description),
    ) -> str:
        # For child resources, check the parent task
        if isinstance(resource_type, TaskChildResourceType):
            task_id = await _get_parent_task_id(
                resource_type, resource_id, event_repository, state_repository
            )
            await authorization.check(
                resource=AgentexResource.task(task_id),
                operation=operation,
            )
        else:
            # For direct resources, check directly
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

        resource = await repository.get(name=resource_id)

        await authorization.check(
            resource=AgentexResource(type=resource_type, selector=resource.id),
            operation=operation,
        )
        return resource_id

    return Annotated[str, Depends(_ensure_authorized_name)]
