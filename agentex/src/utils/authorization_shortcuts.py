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
from src.domain.repositories.task_message_repository import DTaskMessageRepository
from src.domain.repositories.task_repository import DTaskRepository
from src.domain.repositories.task_state_repository import DTaskStateRepository
from src.domain.services.authorization_service import DAuthorizationService
from src.domain.services.schedule_service import build_schedule_id
from src.utils.agent_api_key_authorization import _check_api_key_or_collapse_to_404
from src.utils.schedule_authorization import _check_schedule_or_collapse_to_404


async def _get_parent_task_id(
    resource_type: TaskChildResourceType,
    resource_id: str,
    state_repository: DTaskStateRepository,
    message_repository: DTaskMessageRepository,
) -> str:
    """Get the parent task ID for a task-child resource."""
    registry = {
        TaskChildResourceType.state: state_repository,
        TaskChildResourceType.message: message_repository,
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
        state_repository: DTaskStateRepository,
        message_repository: DTaskMessageRepository,
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
            )
            try:
                await authorization.check(
                    resource=AgentexResource.task(task_id),
                    operation=operation,
                )
            except AuthorizationError:
                raise ItemDoesNotExist(
                    f"Item with id '{resource_id}' does not exist."
                ) from None
        elif resource_type == AgentexResourceType.api_key:
            # Collapse api_key denials to 404 so name/id probes can't
            # distinguish "present in another tenant" from "absent".
            await _check_api_key_or_collapse_to_404(
                authorization, resource_id, operation
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
        state_repository: DTaskStateRepository,
        message_repository: DTaskMessageRepository,
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
            )
            try:
                await authorization.check(
                    resource=AgentexResource.task(task_id),
                    operation=operation,
                )
            except AuthorizationError:
                raise ItemDoesNotExist(
                    f"Item with id '{resource_id}' does not exist."
                ) from None
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

        # Collapse a denied task check into 404 so callers cannot use 403 vs
        # 404 to probe whether a task exists in another tenant.
        # TODO: Refactor to use the canonical task body-id wrap landed by AGX1-275 / #249.
        if resource_type == AgentexResourceType.task:
            try:
                await authorization.check(
                    resource=AgentexResource.task(field_value),
                    operation=operation,
                )
            except AuthorizationError:
                raise ItemDoesNotExist(
                    f"Item with id '{field_value}' does not exist."
                ) from None
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

        resource = await repository.get(name=resource_id)

        await authorization.check(
            resource=AgentexResource(type=resource_type, selector=resource.id),
            operation=operation,
        )
        return resource_id

    return Annotated[str, Depends(_ensure_authorized_name)]


def DAuthorizedScheduleId(
    operation: AuthorizedOperationType = AuthorizedOperationType.read,
):
    """Authorize a single schedule, keyed by the composite ``{agent_id}--
    {schedule_name}`` selector built from the ``agent_id`` and ``schedule_name``
    path params.

    A schedule has no single-id path param (only ``agent_id`` + ``schedule_name``),
    so it can't ride the generic ``DAuthorizedId``. Denials collapse to 404 via
    :func:`_check_schedule_or_collapse_to_404` so callers can't probe
    cross-tenant existence. Returns the ``schedule_name`` for the handler.
    """

    async def _ensure_authorized_schedule(
        authorization: DAuthorizationService,
        agent_id: str = Path(...),
        schedule_name: str = Path(...),
    ) -> str:
        await _check_schedule_or_collapse_to_404(
            authorization,
            build_schedule_id(agent_id, schedule_name),
            operation,
        )
        return schedule_name

    return Annotated[str, Depends(_ensure_authorized_schedule)]
