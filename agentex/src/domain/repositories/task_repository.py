from collections.abc import Sequence
from typing import Annotated, Literal

from fastapi import Depends
from sqlalchemy import select
from src.adapters.crud_store.adapter_postgres import (
    ColumnPrimitiveValue,
    PostgresCRUDRepository,
    async_sql_exception_handler,
)
from src.adapters.orm import AgentORM, AgentTaskTrackerORM, TaskAgentORM, TaskORM
from src.config.dependencies import DDatabaseAsyncReadWriteSessionMaker
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.utils.logging import make_logger

logger = make_logger(__name__)


class TaskRepository(PostgresCRUDRepository[TaskORM, TaskEntity]):
    def __init__(
        self, async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker
    ):
        super().__init__(async_read_write_session_maker, TaskORM, TaskEntity)

    async def list_with_join(
        self,
        *,
        task_filters: dict[str, ColumnPrimitiveValue | Sequence[ColumnPrimitiveValue]]
        | None = None,
        agent_id: str | None = None,
        agent_name: str | None = None,
        order_by: str | None = None,
        order_direction: Literal["asc", "desc"] = "asc",
        limit: int | None = None,
        page_number: int | None = None,
    ) -> list[TaskEntity]:
        """
        List Tasks with custom filters that may require joining tables.

        Args:
            - task_filters (dict[str, ColumnPrimitiveValue | Sequence[ColumnPrimitiveValue]] | None): Filters on the task table itself.
                Keys are column names. Values are either the value to match, or a list of values to match.
            - agent_id (str | None): Filter tasks by agent ID using the join table
            - agent_name (str | None): Filter tasks by agent name
        """

        query = select(TaskORM)
        if agent_id or agent_name:
            query = query.join(TaskAgentORM, TaskORM.id == TaskAgentORM.task_id)
            if agent_name:
                query = query.join(
                    AgentORM, TaskAgentORM.agent_id == AgentORM.id
                ).where(AgentORM.name == agent_name)
            if agent_id:
                query = query.where(TaskAgentORM.agent_id == agent_id)
        query = query.where(TaskORM.status != TaskStatus.DELETED)
        return await self.list(
            filters=task_filters,
            order_by=order_by,
            order_direction=order_direction,
            query=query,
            limit=limit,
            page_number=page_number,
        )

    async def create(self, agent_id: str, task: TaskEntity) -> TaskEntity:
        """Create task and establish agent relationships"""

        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            # Create the task ORM without agents
            task_data = task.to_dict()

            orm = self.orm(**task_data)
            session.add(orm)
            await session.flush()  # Get the task ID

            # Add agent relationships
            task_agent = TaskAgentORM(task_id=orm.id, agent_id=agent_id)
            session.add(task_agent)

            # Create a new agent task tracker
            agent_task_tracker = AgentTaskTrackerORM(
                agent_id=agent_id,
                task_id=orm.id,
                last_processed_event_id=None,
                status=None,
                status_reason=None,
            )
            session.add(agent_task_tracker)
            await session.commit()
            await session.refresh(orm)

            # Return with agents populated
            return TaskEntity.model_validate(orm)

    async def update(self, task: TaskEntity) -> TaskEntity:
        """Update task, preserving agent relationships"""

        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            # Update task fields only (not relationships)
            task_data = task.to_dict()

            orm = self.orm(**task_data)
            modified_orm = await session.merge(orm)
            await session.commit()
            await session.refresh(modified_orm)

            # Return with agents populated
            return TaskEntity.model_validate(modified_orm)


DTaskRepository = Annotated[TaskRepository, Depends(TaskRepository)]
