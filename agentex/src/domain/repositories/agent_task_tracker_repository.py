from typing import Annotated

from fastapi import Depends
from sqlalchemy.future import select
from src.adapters.crud_store.adapter_postgres import (
    PostgresCRUDRepository,
    async_sql_exception_handler,
)
from src.adapters.orm import AgentTaskTrackerORM, EventORM
from src.config.dependencies import DDatabaseAsyncReadWriteSessionMaker
from src.domain.entities.agent_task_tracker import AgentTaskTrackerEntity
from src.utils.logging import make_logger

logger = make_logger(__name__)


class AgentTaskTrackerRepository(
    PostgresCRUDRepository[AgentTaskTrackerORM, AgentTaskTrackerEntity]
):
    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
    ):
        super().__init__(
            async_read_write_session_maker,
            AgentTaskTrackerORM,
            AgentTaskTrackerEntity,
        )

    async def update_agent_task_tracker(
        self,
        id: str,
        status: str,
        status_reason: str | None = None,
        last_processed_event_id: str | None = None,
    ) -> AgentTaskTrackerEntity:
        """
        Commit cursor position for an agent-task combination using SELECT FOR UPDATE.

        Args:
            id: The tracker ID
            status: Processing status
            status_reason: Optional status reason
            last_processed_event_id: The last processed event ID (None to leave unchanged)

        Returns:
            Updated AgentTaskProcessingState object

        Raises:
            ItemDoesNotExist: If processing state doesn't exist
            ValueError: If cursor moves backwards
        """
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            # Lock the row for update
            result = await session.execute(
                select(AgentTaskTrackerORM)
                .where(
                    AgentTaskTrackerORM.id == id,
                )
                .with_for_update()
            )
            current = result.scalar_one()

            # Only validate and update cursor if provided
            if last_processed_event_id is not None:
                # Get the sequence ID of the new event
                new_event_query = select(EventORM.sequence_id).where(
                    EventORM.id == last_processed_event_id
                )
                new_event_result = await session.execute(new_event_query)
                new_sequence_id = new_event_result.scalar_one_or_none()

                if new_sequence_id is None:
                    raise ValueError(
                        f"Event with ID {last_processed_event_id} not found"
                    )

                # Get the sequence ID of the current last processed event
                if current.last_processed_event_id is not None:
                    current_event_query = select(EventORM.sequence_id).where(
                        EventORM.id == current.last_processed_event_id
                    )
                    current_event_result = await session.execute(current_event_query)
                    current_sequence_id = current_event_result.scalar_one_or_none()

                    if (
                        current_sequence_id is not None
                        and new_sequence_id < current_sequence_id
                    ):
                        raise ValueError(
                            f"Cannot move cursor backwards: new sequence ID {new_sequence_id} < current sequence ID {current_sequence_id}"
                        )

                # Update the cursor
                current.last_processed_event_id = last_processed_event_id

            # Always update status fields
            current.status = status
            current.status_reason = status_reason
            # updated_at will be set automatically by onupdate=func.now()

            # Flush to trigger the onupdate and get the updated timestamp
            await session.flush()

            # Refresh the object to get the updated timestamp
            await session.refresh(current)

            # Create the entity while the session is still active
            result = AgentTaskTrackerEntity.model_validate(current)

            await session.commit()

            return result


DAgentTaskTrackerRepository = Annotated[
    AgentTaskTrackerRepository, Depends(AgentTaskTrackerRepository)
]
