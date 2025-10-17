from typing import Annotated, Any

from fastapi import Depends

from src.domain.entities.tasks import TaskEntity
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
        self, id: str | None = None, name: str | None = None
    ) -> TaskEntity:
        """Get task details and current state from ACP server"""
        if not id and not name:
            raise ClientError("Either id or name must be provided")

        return await self.task_service.get_task(id=id, name=name)

    async def update_task(self, task: TaskEntity) -> TaskEntity:
        """Update task record in repository"""
        return await self.task_service.update_task(task=task)

    async def delete_task(self, id: str | None = None, name: str | None = None) -> None:
        """Delete task record from repository"""
        # TODO: Should we notify ACP server about deletion?
        await self.task_service.delete_task(id=id, name=name)

    async def list_tasks(
        self,
        *,
        id: str | list[str] | None = None,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> list[TaskEntity]:
        """List all tasks from repository"""
        return await self.task_service.list_tasks(
            id=id, agent_id=agent_id, agent_name=agent_name
        )

    async def update_mutable_fields_on_task(
        self,
        id: str | None = None,
        name: str | None = None,
        task_metadata: dict[str, Any] | None = None,
    ) -> TaskEntity:
        """Update mutable fields on a task entity. This is used by our API since not all fields should be mutable."""

        if not id and not name:
            raise ClientError("Either id or name must be provided")

        # todo: make this a transaction?
        task_entity = await self.task_service.get_task(id=id, name=name)

        # if no mutations are provided, don't do anything
        if task_metadata is None:
            return task_entity

        if task_metadata is not None:
            task_entity.task_metadata = task_metadata

        updated_task_entity = await self.task_service.update_task(task=task_entity)
        return updated_task_entity


DTaskUseCase = Annotated[TasksUseCase, Depends(TasksUseCase)]
