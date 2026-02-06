from typing import Annotated, Any

from fastapi import Depends

from src.domain.entities.states import StateEntity
from src.domain.repositories.task_state_dual_repository import DTaskStateDualRepository
from src.utils.logging import make_logger

logger = make_logger(__name__)


class StatesUseCase:
    def __init__(
        self,
        task_state_repository: DTaskStateDualRepository,
    ):
        self.task_state_repository = task_state_repository

    async def create(
        self, task_id: str, agent_id: str, state: dict[str, Any]
    ) -> StateEntity:
        state = StateEntity(
            task_id=task_id,
            agent_id=agent_id,
            state=state,
        )
        return await self.task_state_repository.create(state)

    async def get(self, id: str) -> StateEntity | None:
        return await self.task_state_repository.get(id=id)

    async def list(
        self,
        limit: int,
        page_number: int,
        task_id: str | None = None,
        agent_id: str | None = None,
        order_by: str | None = None,
        order_direction: str = "desc",
    ) -> list[StateEntity]:
        filters = {}
        if task_id:
            filters["task_id"] = task_id
        if agent_id:
            filters["agent_id"] = agent_id

        return await self.task_state_repository.list(
            filters=filters if filters else None,
            limit=limit,
            page_number=page_number,
            order_by=order_by,
            order_direction=order_direction,
        )

    async def update(self, id: str, task_id: str, state: dict[str, Any]) -> StateEntity:
        task_state = await self.task_state_repository.get(id=id)
        if task_state and task_state.task_id == task_id:
            # Update the state field but preserve other fields
            task_state.state = state
            return await self.task_state_repository.update(task_state)
        return task_state

    async def delete(self, id: str) -> None:
        return await self.task_state_repository.delete(id=id)


DStatesUseCase = Annotated[StatesUseCase, Depends(StatesUseCase)]
