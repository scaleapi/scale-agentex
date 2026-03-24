"""
Unit tests for TasksUseCase - specifically the status transition logic
via explicit status methods (complete_task, fail_task, etc.).
"""

from uuid import uuid4

import pytest
from src.adapters.crud_store.exceptions import DuplicateItemError, ItemDoesNotExist
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.entities.tasks import TaskStatus
from src.domain.exceptions import ClientError
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.use_cases.tasks_use_case import TasksUseCase


async def create_or_get_agent(agent_repository, agent):
    """Helper to create agent or get existing one if name already exists"""
    try:
        return await agent_repository.create(agent)
    except DuplicateItemError:
        existing_agent = await agent_repository.get(name=agent.name)
        agent.id = existing_agent.id
        return existing_agent


@pytest.fixture
def agent_repository(postgres_session_maker):
    """Real AgentRepository using test PostgreSQL database"""
    return AgentRepository(postgres_session_maker, postgres_session_maker)


@pytest.fixture
def task_repository(postgres_session_maker):
    """Real TaskRepository using test PostgreSQL database"""
    return TaskRepository(postgres_session_maker, postgres_session_maker)


@pytest.fixture
def tasks_use_case(task_service):
    """TasksUseCase with real task_service"""
    return TasksUseCase(task_service=task_service)


@pytest.fixture
def sample_agent():
    """Sample agent entity for testing"""
    return AgentEntity(
        id=str(uuid4()),
        name="test-agent-use-case",
        description="A test agent for use case testing",
        status=AgentStatus.READY,
        acp_type=ACPType.ASYNC,
        acp_url="http://test-acp.example.com",
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestTasksUseCaseStatusTransitions:
    """Test suite for task status transitions via explicit status methods"""

    async def test_complete_running_task(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that a RUNNING task can be transitioned to COMPLETED"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="complete-test"
        )
        assert task.status == TaskStatus.RUNNING

        # When
        updated = await tasks_use_case.complete_task(
            id=task.id, reason="Agent finished"
        )

        # Then
        assert updated.status == TaskStatus.COMPLETED
        assert updated.status_reason == "Agent finished"

    async def test_terminate_running_task(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that a RUNNING task can be transitioned to TERMINATED"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="terminate-test"
        )

        # When
        updated = await tasks_use_case.terminate_task(
            id=task.id, reason="Workflow killed"
        )

        # Then
        assert updated.status == TaskStatus.TERMINATED
        assert updated.status_reason == "Workflow killed"

    async def test_timeout_running_task(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that a RUNNING task can be transitioned to TIMED_OUT"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="timeout-test"
        )

        # When
        updated = await tasks_use_case.timeout_task(id=task.id)

        # Then
        assert updated.status == TaskStatus.TIMED_OUT
        assert updated.status_reason == "Task timed_out"

    async def test_default_status_reason(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that a default status_reason is set when none provided"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="default-reason-test"
        )

        # When
        updated = await tasks_use_case.complete_task(id=task.id)

        # Then
        assert updated.status_reason == "Task completed"

    async def test_cannot_transition_completed_task(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that a COMPLETED task cannot be transitioned again"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="double-complete-test"
        )
        await tasks_use_case.complete_task(id=task.id)

        # When / Then
        with pytest.raises(ClientError, match="not running"):
            await tasks_use_case.terminate_task(id=task.id)

    async def test_cannot_transition_canceled_task(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that a CANCELED task cannot be transitioned"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="cancel-block-test"
        )
        await tasks_use_case.cancel_task(id=task.id)

        # When / Then
        with pytest.raises(ClientError, match="not running"):
            await tasks_use_case.complete_task(id=task.id)

    async def test_cannot_transition_failed_task(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that a FAILED task cannot be transitioned"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="fail-block-test"
        )
        await tasks_use_case.fail_task(id=task.id)

        # When / Then
        with pytest.raises(ClientError, match="not running"):
            await tasks_use_case.complete_task(id=task.id)

    async def test_cannot_transition_deleted_task(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that a DELETED task raises not found"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="delete-block-test"
        )
        await tasks_use_case.delete_task(id=task.id)

        # When / Then
        with pytest.raises(ItemDoesNotExist):
            await tasks_use_case.complete_task(id=task.id)

    async def test_update_metadata_without_status(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that updating only task_metadata does not change status"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="metadata-only-test"
        )

        # When
        updated = await tasks_use_case.update_task_metadata(
            id=task.id, task_metadata={"key": "value"}
        )

        # Then
        assert updated.status == TaskStatus.RUNNING
        assert updated.task_metadata == {"key": "value"}
