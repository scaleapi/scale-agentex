"""
Unit tests for TasksUseCase - status transition logic via explicit status
methods (complete_task, fail_task, etc.) and metadata updates.
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

    # --- Happy-path transitions (RUNNING -> terminal) ---

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

    async def test_fail_running_task(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that a RUNNING task can be transitioned to FAILED"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(agent=sample_agent, task_name="fail-test")

        # When
        updated = await tasks_use_case.fail_task(
            id=task.id, reason="Something went wrong"
        )

        # Then
        assert updated.status == TaskStatus.FAILED
        assert updated.status_reason == "Something went wrong"

    async def test_cancel_running_task(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that a RUNNING task can be transitioned to CANCELED"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="cancel-test"
        )

        # When
        updated = await tasks_use_case.cancel_task(
            id=task.id, reason="User requested cancellation"
        )

        # Then
        assert updated.status == TaskStatus.CANCELED
        assert updated.status_reason == "User requested cancellation"

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

    # --- Default reason for each transition ---

    @pytest.mark.parametrize(
        "method,expected_reason",
        [
            ("complete_task", "Task completed"),
            ("fail_task", "Task failed"),
            ("cancel_task", "Task canceled"),
            ("terminate_task", "Task terminated"),
            ("timeout_task", "Task timed_out"),
        ],
    )
    async def test_default_status_reason(
        self,
        tasks_use_case,
        task_service,
        agent_repository,
        sample_agent,
        method,
        expected_reason,
    ):
        """Test that each transition method sets a default reason when none provided"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name=f"default-reason-{method}"
        )

        # When
        updated = await getattr(tasks_use_case, method)(id=task.id)

        # Then
        assert updated.status_reason == expected_reason

    # --- Transition by name ---

    async def test_complete_task_by_name(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that a task can be transitioned using name instead of id"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="complete-by-name-test"
        )

        # When
        updated = await tasks_use_case.complete_task(
            name=task.name, reason="Done by name"
        )

        # Then
        assert updated.status == TaskStatus.COMPLETED
        assert updated.status_reason == "Done by name"

    # --- Blocked transitions from each terminal state ---

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

    async def test_cannot_transition_terminated_task(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that a TERMINATED task cannot be transitioned"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="terminate-block-test"
        )
        await tasks_use_case.terminate_task(id=task.id)

        # When / Then
        with pytest.raises(ClientError, match="not running"):
            await tasks_use_case.complete_task(id=task.id)

    async def test_cannot_transition_timed_out_task(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that a TIMED_OUT task cannot be transitioned"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="timeout-block-test"
        )
        await tasks_use_case.timeout_task(id=task.id)

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

    # --- Validation ---

    async def test_transition_requires_id_or_name(self, tasks_use_case):
        """Test that transitioning without id or name raises ClientError"""
        with pytest.raises(ClientError, match="Either id or name must be provided"):
            await tasks_use_case.complete_task()


@pytest.mark.unit
@pytest.mark.asyncio
class TestTasksUseCaseMetadataUpdate:
    """Test suite for update_mutable_fields_on_task"""

    async def test_update_metadata(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that task_metadata is replaced with the provided value"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="metadata-update-test"
        )

        # When
        updated = await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, task_metadata={"key": "value"}
        )

        # Then
        assert updated.task_metadata == {"key": "value"}
        assert updated.status == TaskStatus.RUNNING

    async def test_update_metadata_does_not_change_status(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that updating metadata leaves status unchanged"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="metadata-status-test"
        )

        # When
        updated = await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, task_metadata={"new": "data"}
        )

        # Then
        assert updated.status == TaskStatus.RUNNING

    async def test_update_metadata_replaces_existing(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that metadata is fully replaced, not merged"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="metadata-replace-test"
        )
        await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, task_metadata={"original": "data", "keep": "this"}
        )

        # When
        updated = await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, task_metadata={"replaced": "entirely"}
        )

        # Then
        assert updated.task_metadata == {"replaced": "entirely"}
        assert "original" not in updated.task_metadata

    async def test_update_metadata_with_empty_dict(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that metadata can be set to an empty dict"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="metadata-empty-test"
        )
        await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, task_metadata={"some": "data"}
        )

        # When
        updated = await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, task_metadata={}
        )

        # Then
        assert updated.task_metadata == {}

    async def test_update_metadata_noop_when_none(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that passing task_metadata=None is a no-op"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="metadata-noop-test"
        )

        # When
        updated = await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, task_metadata=None
        )

        # Then
        assert updated.id == task.id
        assert updated.task_metadata == task.task_metadata

    async def test_update_metadata_by_name(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that metadata can be updated using task name"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="metadata-by-name-test"
        )

        # When
        updated = await tasks_use_case.update_mutable_fields_on_task(
            name=task.name, task_metadata={"via": "name"}
        )

        # Then
        assert updated.task_metadata == {"via": "name"}

    async def test_update_metadata_on_deleted_task_raises(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Test that updating metadata on a deleted task raises not found"""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="metadata-deleted-test"
        )
        await tasks_use_case.delete_task(id=task.id)

        # When / Then
        with pytest.raises(ItemDoesNotExist):
            await tasks_use_case.update_mutable_fields_on_task(
                id=task.id, task_metadata={"should": "fail"}
            )

    async def test_update_metadata_requires_id_or_name(self, tasks_use_case):
        """Test that updating metadata without id or name raises ClientError"""
        with pytest.raises(ClientError, match="Either id or name must be provided"):
            await tasks_use_case.update_mutable_fields_on_task(
                task_metadata={"key": "value"}
            )
