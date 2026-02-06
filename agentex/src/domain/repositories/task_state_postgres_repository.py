from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import and_, select, update
from src.adapters.crud_store.adapter_postgres import (
    PostgresCRUDRepository,
    async_sql_exception_handler,
)
from src.adapters.orm import TaskStateORM
from src.config.dependencies import (
    DDatabaseAsyncReadOnlySessionMaker,
    DDatabaseAsyncReadWriteSessionMaker,
)
from src.domain.entities.states import StateEntity
from src.utils.logging import make_logger

logger = make_logger(__name__)


class TaskStatePostgresRepository(PostgresCRUDRepository[TaskStateORM, StateEntity]):
    """Repository for managing task states in PostgreSQL."""

    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
        async_read_only_session_maker: DDatabaseAsyncReadOnlySessionMaker,
    ):
        super().__init__(
            async_read_write_session_maker,
            async_read_only_session_maker,
            TaskStateORM,
            StateEntity,
        )

    async def get_by_task_and_agent(
        self, task_id: str, agent_id: str
    ) -> StateEntity | None:
        """Get state by the unique combination of task_id and agent_id."""
        async with (
            self.start_async_db_session(allow_writes=False) as session,
            async_sql_exception_handler(),
        ):
            query = select(TaskStateORM).where(
                and_(
                    TaskStateORM.task_id == task_id,
                    TaskStateORM.agent_id == agent_id,
                )
            )
            result = await session.execute(query)
            orm_result = result.scalar_one_or_none()
            return StateEntity.model_validate(orm_result) if orm_result else None

    async def update(self, item: StateEntity) -> StateEntity:
        """
        Update a task state using UPDATE ... RETURNING for single round-trip.

        This overrides the parent class's update method which uses merge() + refresh()
        (2 round trips) with a more efficient single-statement approach.
        """
        async with (
            self.start_async_db_session(allow_writes=True) as session,
            async_sql_exception_handler(),
        ):
            stmt = (
                update(TaskStateORM)
                .where(TaskStateORM.id == item.id)
                .values(**item.to_dict())
                .returning(TaskStateORM)
            )
            result = await session.execute(stmt)
            await session.commit()
            updated_orm = result.scalar_one()
            return StateEntity.model_validate(updated_orm)

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        page_number: int | None = None,
        order_by: str | None = None,
        order_direction: str | None = None,
    ) -> list[StateEntity]:
        """List states with optional filtering and pagination."""
        return await super().list(
            filters=filters,
            order_by=order_by or "created_at",
            order_direction=order_direction or "desc",
            limit=limit,
            page_number=page_number,
        )


DTaskStatePostgresRepository = Annotated[
    TaskStatePostgresRepository, Depends(TaskStatePostgresRepository)
]
