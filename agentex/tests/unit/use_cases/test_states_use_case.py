from unittest.mock import AsyncMock

import pytest
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.domain.entities.states import StateEntity
from src.domain.repositories.task_state_repository import TaskStateRepository
from src.domain.use_cases.states_use_case import StatesUseCase


@pytest.fixture
def task_state_repository():
    repository = AsyncMock(spec=TaskStateRepository)
    repository.get = AsyncMock()
    repository.update = AsyncMock()
    return repository


@pytest.fixture
def states_use_case(task_state_repository):
    return StatesUseCase(task_state_repository=task_state_repository)


@pytest.fixture
def existing_state():
    return StateEntity(
        id="state-1",
        task_id="task-1",
        agent_id="agent-1",
        state={"status": "old"},
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestStatesUseCase:
    async def test_update_mutates_state_by_id(
        self, states_use_case, task_state_repository, existing_state
    ):
        task_state_repository.get.return_value = existing_state
        task_state_repository.update.return_value = existing_state

        result = await states_use_case.update(
            id="state-1",
            state={"status": "new"},
        )

        assert result is existing_state
        assert result.state == {"status": "new"}
        task_state_repository.get.assert_awaited_once_with(id="state-1")
        task_state_repository.update.assert_awaited_once_with(existing_state)

    async def test_update_raises_not_found_when_state_does_not_exist(
        self, states_use_case, task_state_repository
    ):
        task_state_repository.get.return_value = None

        with pytest.raises(ItemDoesNotExist) as exc_info:
            await states_use_case.update(
                id="state-1",
                state={"status": "new"},
            )

        assert "State state-1 not found" in str(exc_info.value)
        task_state_repository.get.assert_awaited_once_with(id="state-1")
        task_state_repository.update.assert_not_awaited()
