from typing import Annotated, Any

from fastapi import Depends

from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.domain.entities.tasks import TaskEntity, TaskRelationships, TaskStatus
from src.domain.exceptions import ClientError
from src.domain.services.task_service import DAgentTaskService
from src.utils.logging import make_logger

logger = make_logger(__name__)


class TasksUseCase:
    """
    Use case for managing tasks. Handles CRUD operations and delegates task operations to ACP servers.
    """

    def __init__(
        self,
        task_service: DAgentTaskService,
    ):
        self.task_service = task_service

    async def get_task(
        self,
        id: str | None = None,
        name: str | None = None,
        relationships: list[TaskRelationships] | None = None,
    ) -> TaskEntity:
        """Get task details and current state from ACP server"""
        if not id and not name:
            raise ClientError("Either id or name must be provided")

        task = await self.task_service.get_task(
            id=id, name=name, relationships=relationships
        )
        if task.status == TaskStatus.DELETED:
            if id:
                raise ItemDoesNotExist(f"Task {id} not found")
            else:
                raise ItemDoesNotExist(f"Task {name} not found")
        return task

    async def update_task(self, task: TaskEntity) -> TaskEntity:
        """Update task record in repository"""
        if task.status == TaskStatus.DELETED:
            raise ItemDoesNotExist(f"Task {task.id} not found")
        return await self.task_service.update_task(task=task)

    async def delete_task(self, id: str | None = None, name: str | None = None) -> None:
        """Delete task record from repository"""
        # TODO: Should we notify ACP server about deletion?
        task = await self.task_service.get_task(id=id, name=name)
        if task.status == TaskStatus.DELETED:
            if id:
                raise ItemDoesNotExist(f"Task {id} not found")
            else:
                raise ItemDoesNotExist(f"Task {name} not found")
        task.status = TaskStatus.DELETED
        task.status_reason = "Task deleted successfully"
        await self.task_service.update_task(task=task)

    async def list_tasks(
        self,
        *,
        limit: int,
        page_number: int,
        id: str | list[str] | None = None,
        agent_id: str | None = None,
        agent_name: str | None = None,
        order_by: str | None = None,
        order_direction: str = "desc",
        relationships: list[TaskRelationships] | None = None,
    ) -> list[TaskEntity]:
        """List all tasks from repository"""
        return await self.task_service.list_tasks(
            id=id,
            agent_id=agent_id,
            agent_name=agent_name,
            limit=limit,
            page_number=page_number,
            order_by=order_by,
            order_direction=order_direction,
            relationships=relationships,
        )

    async def update_mutable_fields_on_task(
        self,
        id: str | None = None,
        name: str | None = None,
        task_metadata: dict[str, Any] | None = None,
        status: TaskStatus | None = None,
        status_reason: str | None = None,
    ) -> TaskEntity:
        """Update mutable fields on a task entity. This is used by our API since not all fields should be mutable."""

        if not id and not name:
            raise ClientError("Either id or name must be provided")

        task_entity = await self.task_service.get_task(id=id, name=name)
        if task_entity.status == TaskStatus.DELETED:
            identifier = id or name
            raise ItemDoesNotExist(f"Task {identifier} not found")

        # If no mutations were provided, don't write
        if status is None and task_metadata is None:
            return task_entity

        # Status transition uses an atomic conditional update to prevent race conditions
        if status is not None:
            if task_entity.status != TaskStatus.RUNNING:
                raise ClientError(
                    f"Task {task_entity.id} is not running (current status: {task_entity.status}). "
                    f"Only running tasks can have their status updated."
                )
            reason = status_reason or f"Task {status.value.lower()}"
            updated = await self.task_service.transition_task_status(
                task_id=task_entity.id,
                expected_status=TaskStatus.RUNNING,
                new_status=status,
                status_reason=reason,
                task_metadata=task_metadata,
            )
            if updated is None:
                raise ClientError(
                    f"Task {task_entity.id} status was concurrently modified. "
                    f"Please retry the request."
                )
            return updated

        # Metadata-only update (no status change)
        task_entity.task_metadata = task_metadata
        return await self.task_service.update_task(task=task_entity)


DTaskUseCase = Annotated[TasksUseCase, Depends(TasksUseCase)]
