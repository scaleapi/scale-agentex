import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from src.adapters.crud_store.exceptions import DuplicateItemError
from src.api.schemas.task_message_updates import (
    DeltaType,
    StreamTaskMessageDelta,
    TaskMessageUpdateType,
    TextDelta,
)
from src.api.schemas.task_messages import TextContent
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.entities.task_messages import MessageAuthor
from src.domain.entities.tasks import TaskEntity, TaskFailureSource, TaskStatus
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.repositories.event_repository import EventRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.repositories.task_state_repository import TaskStateRepository
from src.domain.services.task_service import AgentTaskService

from tests.fixtures.services import make_noop_authorization_service

RACE_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


async def create_or_get_agent(agent_repository, agent):
    """Helper to create agent or get existing one if name already exists"""
    try:
        return await agent_repository.create(agent)
    except DuplicateItemError:
        # Agent with this name already exists, get it by name
        existing_agent = await agent_repository.get(name=agent.name)
        # Update the passed-in agent's ID to match the database version
        # so foreign key constraints work properly
        agent.id = existing_agent.id
        return existing_agent


@pytest.fixture
def mock_acp_client():
    """Mock ACP client for testing service interactions (external dependency)"""
    mock = AsyncMock()
    mock.create_task = AsyncMock()
    mock.send_message = AsyncMock()
    mock.send_message_stream = AsyncMock()
    mock.cancel_task = AsyncMock()
    mock.send_event = AsyncMock()
    return mock


class InMemoryTaskStatusRepository:
    """Minimal status repository used to control CAS race ordering."""

    def __init__(self, task: TaskEntity):
        self.task = task.model_copy()
        self.claim_requests = 0
        self.transition_requests = []
        self.current_reads = 0

    async def claim_acp_forward(self, task_id):
        assert task_id == self.task.id
        self.claim_requests += 1
        eligible = self.task.status in {
            TaskStatus.RUNNING,
            TaskStatus.INTERRUPTED,
        } or (
            self.task.status == TaskStatus.FAILED
            and self.task.failure_source == TaskFailureSource.ACP_FORWARD
        )
        if not eligible:
            return None

        updated_at = (self.task.updated_at or RACE_TIMESTAMP) + timedelta(
            microseconds=1
        )
        self.task = self.task.model_copy(
            update={
                "status": TaskStatus.RUNNING,
                "status_reason": "Forwarding task to ACP server",
                "failure_source": TaskFailureSource.ACP_FORWARD,
                "updated_at": updated_at,
            }
        )
        return self.task.model_copy()

    async def transition_status(
        self,
        task_id,
        expected_status,
        new_status,
        status_reason,
        task_metadata=None,
        expected_updated_at=None,
        expected_failure_source=None,
        new_failure_source=None,
    ):
        assert task_id == self.task.id
        self.transition_requests.append(expected_status)
        eligible_statuses = (
            (expected_status,)
            if isinstance(expected_status, TaskStatus)
            else expected_status
        )
        if self.task.status not in eligible_statuses:
            return None
        if (
            expected_updated_at is not None
            and self.task.updated_at != expected_updated_at
        ):
            return None
        if (
            expected_failure_source is not None
            and self.task.failure_source != expected_failure_source
        ):
            return None

        updates = {
            "status": new_status,
            "status_reason": status_reason,
            "failure_source": new_failure_source,
        }
        if task_metadata is not None:
            updates["task_metadata"] = task_metadata
        updates["updated_at"] = self.task.updated_at + timedelta(microseconds=1)
        self.task = self.task.model_copy(update=updates)
        return self.task.model_copy()

    async def get(self, **_kwargs):
        return self.task.model_copy()

    async def get_current(self, _task_id=None, **_kwargs):
        self.current_reads += 1
        return self.task.model_copy()

    async def replace_metadata(self, task_id, task_metadata):
        assert task_id == self.task.id
        updated_at = (self.task.updated_at or RACE_TIMESTAMP) + timedelta(
            microseconds=1
        )
        self.task = self.task.model_copy(
            update={"task_metadata": task_metadata, "updated_at": updated_at}
        )
        return self.task.model_copy()


def make_task_service_for_status_race(mock_acp_client, task_repository):
    """Build a service around a deterministic in-memory status repository."""
    return AgentTaskService(
        acp_client=mock_acp_client,
        task_repository=task_repository,
        task_state_repository=AsyncMock(),
        event_repository=AsyncMock(),
        stream_repository=AsyncMock(),
        authorization_service=make_noop_authorization_service(),
    )


@pytest.fixture
def task_repository(postgres_session_maker):
    """Real TaskRepository using test PostgreSQL database"""
    return TaskRepository(postgres_session_maker, postgres_session_maker)


@pytest.fixture
def agent_repository(postgres_session_maker):
    """Real AgentRepository using test PostgreSQL database"""
    return AgentRepository(postgres_session_maker, postgres_session_maker)


@pytest.fixture
def task_state_repository(mongodb_database):
    """Real TaskStateRepository using test MongoDB database"""
    return TaskStateRepository(mongodb_database)


@pytest.fixture
def event_repository(postgres_session_maker):
    """Real EventRepository using test PostgreSQL database"""
    return EventRepository(postgres_session_maker, postgres_session_maker)


@pytest.fixture
def task_service(
    mock_acp_client,
    task_repository,
    task_state_repository,
    event_repository,
    redis_stream_repository,
):
    """Create TaskService instance with real repositories and mocked ACP client"""
    return AgentTaskService(
        acp_client=mock_acp_client,
        task_repository=task_repository,
        task_state_repository=task_state_repository,
        event_repository=event_repository,
        stream_repository=redis_stream_repository,
        authorization_service=make_noop_authorization_service(),
    )


@pytest.fixture
def sample_agent():
    """Sample agent entity for testing"""
    return AgentEntity(
        id=str(uuid4()),
        name="test-agent",
        description="A test agent for unit testing",
        status=AgentStatus.READY,
        acp_type=ACPType.ASYNC,
        acp_url="http://test-acp.example.com",
    )


@pytest.fixture
def sample_sync_agent():
    """Sample sync agent entity for testing sync workflows"""
    return AgentEntity(
        id=str(uuid4()),
        name="sync-agent",
        description="A sync agent for testing synchronous workflows",
        status=AgentStatus.READY,
        acp_type=ACPType.SYNC,
        acp_url="http://sync-acp.example.com",
    )


@pytest.fixture
def sample_task():
    """Sample task entity for testing"""
    return TaskEntity(
        id=str(uuid4()),
        name="test-task",
        status=TaskStatus.RUNNING,
        status_reason="Task is running",
    )


@pytest.fixture
def sample_message_content():
    """Sample message content for testing"""
    return TextContent(
        content="Hello, this is a test message", author=MessageAuthor.USER
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentTaskService:
    """Test suite for AgentTaskService"""

    async def test_create_task_success(
        self, task_service, sample_agent, agent_repository
    ):
        """Test successful task creation"""
        # Given - Persist the agent first to satisfy foreign key constraints
        await create_or_get_agent(agent_repository, sample_agent)

        # When
        result = await task_service.create_task(
            agent=sample_agent, task_name="integration-test"
        )

        # Then
        assert result is not None
        assert result.id is not None
        assert result.name == "integration-test"
        assert result.status == TaskStatus.RUNNING
        assert result.status_reason == "Task created, forwarding to ACP server"

    async def test_create_task_without_name(
        self, task_service, task_repository, agent_repository, sample_agent
    ):
        """Test task creation without specifying name"""
        # Given - Persist the agent first to satisfy foreign key constraints
        await create_or_get_agent(agent_repository, sample_agent)

        # When
        result = await task_service.create_task(agent=sample_agent)

        # Then
        assert result is not None
        assert result.id is not None
        assert result.name is None
        assert result.status == TaskStatus.RUNNING
        assert result.status_reason == "Task created, forwarding to ACP server"

    async def test_create_task_with_params(
        self, task_service, agent_repository, sample_agent
    ):
        """Test task creation with params"""
        # Given - Persist the agent first to satisfy foreign key constraints
        await create_or_get_agent(agent_repository, sample_agent)
        task_params = {
            "model": "gpt-4",
            "temperature": 0.7,
            "max_tokens": 1000,
            "nested": {"key": "value", "array": [1, 2, 3]},
        }

        # When
        result = await task_service.create_task(
            agent=sample_agent, task_name="task-with-params", task_params=task_params
        )

        # Then
        assert result is not None
        assert result.id is not None
        assert result.name == "task-with-params"
        assert result.params == task_params
        assert result.status == TaskStatus.RUNNING
        assert result.status_reason == "Task created, forwarding to ACP server"

    async def test_create_task_with_params_retrieval(
        self, task_service, agent_repository, sample_agent
    ):
        """Test that created task with params can be retrieved correctly"""
        # Given - Persist the agent first to satisfy foreign key constraints
        await create_or_get_agent(agent_repository, sample_agent)
        task_params = {
            "config": {"setting1": True, "setting2": "value"},
            "metadata": {"version": "1.0", "priority": 5},
        }

        # When - Create task with params
        created_task = await task_service.create_task(
            agent=sample_agent,
            task_name="retrievable-params-task",
            task_params=task_params,
        )

        # Then - Retrieve by ID and verify params are preserved
        retrieved_by_id = await task_service.get_task(id=created_task.id)
        assert retrieved_by_id.params == task_params

        # Then - Retrieve by name and verify params are preserved
        retrieved_by_name = await task_service.get_task(name="retrievable-params-task")
        assert retrieved_by_name.params == task_params

    async def test_create_task_with_null_params(
        self, task_service, agent_repository, sample_agent
    ):
        """Test task creation with null params"""
        # Given - Persist the agent first to satisfy foreign key constraints
        await create_or_get_agent(agent_repository, sample_agent)

        # When
        result = await task_service.create_task(
            agent=sample_agent, task_name="task-null-params", task_params=None
        )

        # Then
        assert result is not None
        assert result.id is not None
        assert result.name == "task-null-params"
        assert result.params is None
        assert result.status == TaskStatus.RUNNING

        # Verify retrieval preserves null params
        retrieved_task = await task_service.get_task(id=result.id)
        assert retrieved_task.params is None

    async def test_create_task_and_forward_to_acp_success(
        self,
        task_service,
        mock_acp_client,
        task_repository,
        agent_repository,
        sample_agent,
    ):
        """Test successful task creation and ACP forwarding"""
        # Given - Persist the agent first to satisfy foreign key constraints
        await create_or_get_agent(agent_repository, sample_agent)
        task_params = {"param1": "value1", "param2": "value2"}
        mock_acp_client.create_task.return_value = None

        # When
        result = await task_service.create_task_and_forward_to_acp(
            agent=sample_agent, task_name="forwarded-task", task_params=task_params
        )

        # Then
        assert result is not None
        assert result.id is not None
        assert result.name == "forwarded-task"
        assert result.params == task_params  # Verify params are stored in the task
        assert result.status == TaskStatus.RUNNING
        assert result.status_reason == "Task forwarded to ACP server"

        # Verify ACP client was called with correct parameters
        mock_acp_client.create_task.assert_awaited_once()
        forwarded_call = mock_acp_client.create_task.await_args.kwargs
        assert forwarded_call["agent"] == sample_agent
        assert forwarded_call["task"].id == result.id
        assert forwarded_call["acp_url"] == sample_agent.acp_url
        assert forwarded_call["params"] == task_params

    async def test_create_task_and_forward_sync_agent_skips_acp(
        self,
        task_service,
        mock_acp_client,
        task_repository,
        agent_repository,
        sample_sync_agent,
    ):
        """Test that sync agents skip ACP forwarding"""
        # Given - Persist the agent first to satisfy foreign key constraints
        await create_or_get_agent(agent_repository, sample_sync_agent)

        # When
        result = await task_service.create_task_and_forward_to_acp(
            agent=sample_sync_agent, task_name="sync-task"
        )

        # Then
        assert result is not None
        assert result.id is not None
        assert result.name == "sync-task"
        assert result.status == TaskStatus.RUNNING
        assert result.status_reason == "Task created, forwarding to ACP server"

        # Verify ACP client was NOT called for sync agents
        mock_acp_client.create_task.assert_not_called()

    async def test_create_task_and_forward_acp_error_handling(
        self,
        task_service,
        mock_acp_client,
        task_repository,
        agent_repository,
        sample_agent,
    ):
        """Test error handling when ACP forwarding fails"""
        # Given - Persist the agent first to satisfy foreign key constraints
        await create_or_get_agent(agent_repository, sample_agent)
        acp_error = Exception("ACP server unavailable")
        mock_acp_client.create_task.side_effect = acp_error

        # When / Then
        with pytest.raises(Exception) as exc_info:
            await task_service.create_task_and_forward_to_acp(agent=sample_agent)

        assert str(exc_info.value) == "ACP server unavailable"

        # Verify task was created but then marked as failed due to ACP error
        mock_acp_client.create_task.assert_called_once()

    async def test_fail_task(
        self, task_service, task_repository, agent_repository, sample_agent
    ):
        """Test task failure handling"""
        # Given - Create a real task in the database
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="task-to-fail"
        )
        reason = "Connection timeout"

        # When
        await task_service.fail_task(created_task, reason)

        # Then
        assert created_task.status == TaskStatus.FAILED
        assert created_task.status_reason == reason

        # Verify task is updated in database
        updated_task = await task_service.get_task(id=created_task.id)
        assert updated_task.status == TaskStatus.FAILED
        assert updated_task.status_reason == reason

    async def test_forward_task_to_acp_clears_stale_failed_status(
        self,
        task_service,
        mock_acp_client,
        task_repository,
        agent_repository,
        sample_agent,
    ):
        """A task left FAILED by a forward attempt while the agent was down is
        reset to RUNNING once a later forward succeeds.

        Regression test: previously forward_task_to_acp only ever wrote status
        on failure, so a task that failed to forward while the agent was
        unavailable stayed FAILED forever even after the agent recovered and the
        workflow was actually created — making the task/create RPC response
        report a misleading failure.
        """
        # Given - an agent and a task that fails to forward while the agent is down
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="recovering-task"
        )
        mock_acp_client.create_task.side_effect = Exception(
            "All connection attempts failed"
        )
        with pytest.raises(Exception, match="All connection attempts failed"):
            await task_service.forward_task_to_acp(agent=sample_agent, task=task)

        failed = await task_service.get_task(id=task.id)
        assert failed.status == TaskStatus.FAILED
        assert failed.status_reason == "All connection attempts failed"
        assert failed.failure_source == TaskFailureSource.ACP_FORWARD

        # When - the agent recovers and the same task is forwarded again
        mock_acp_client.create_task.side_effect = None
        mock_acp_client.create_task.return_value = None
        result = await task_service.forward_task_to_acp(agent=sample_agent, task=failed)

        # Then - the returned task and the persisted row reflect RUNNING again
        assert result.status == TaskStatus.RUNNING
        assert result.status_reason == "Task forwarded to ACP server"
        assert result.failure_source is None
        refreshed = await task_service.get_task(id=task.id)
        assert refreshed.status == TaskStatus.RUNNING
        assert refreshed.status_reason == "Task forwarded to ACP server"
        assert refreshed.failure_source is None

    async def test_workflow_owned_failed_task_is_not_forwarded(
        self,
        mock_acp_client,
        sample_agent,
    ):
        """A workflow-owned failure is terminal, not a retry admission signal."""
        failed = TaskEntity(
            id=str(uuid4()),
            name="workflow-failed-task",
            status=TaskStatus.FAILED,
            status_reason="Workflow validation failed",
            updated_at=RACE_TIMESTAMP,
        )
        repository = InMemoryTaskStatusRepository(failed)
        task_service = make_task_service_for_status_race(mock_acp_client, repository)

        result = await task_service.forward_task_to_acp(
            agent=sample_agent,
            task=failed,
        )

        assert result.status == TaskStatus.FAILED
        assert result.status_reason == "Workflow validation failed"
        assert result.failure_source is None
        assert repository.claim_requests == 1
        assert repository.transition_requests == []
        mock_acp_client.create_task.assert_not_awaited()

    async def test_failed_forward_retry_is_claimed_before_acp_call(
        self,
        mock_acp_client,
        sample_agent,
    ):
        """ACP observes RUNNING, never the retryable FAILED snapshot."""
        failed = TaskEntity(
            id=str(uuid4()),
            name="preclaimed-retry",
            status=TaskStatus.FAILED,
            status_reason="Connection lost",
            failure_source=TaskFailureSource.ACP_FORWARD,
            updated_at=RACE_TIMESTAMP,
        )
        repository = InMemoryTaskStatusRepository(failed)
        task_service = make_task_service_for_status_race(mock_acp_client, repository)

        async def assert_claimed_before_forward(**kwargs):
            forwarded = kwargs["task"]
            assert forwarded.status == TaskStatus.RUNNING
            assert forwarded.failure_source == TaskFailureSource.ACP_FORWARD
            assert repository.task.status == TaskStatus.RUNNING

        mock_acp_client.create_task.side_effect = assert_claimed_before_forward

        result = await task_service.forward_task_to_acp(
            agent=sample_agent,
            task=failed,
        )

        assert result.status == TaskStatus.RUNNING
        assert result.failure_source is None
        assert repository.claim_requests == 1
        assert repository.transition_requests == [
            (TaskStatus.RUNNING, TaskStatus.FAILED)
        ]

    async def test_running_forward_recovery_can_take_over_after_claiming_process_dies(
        self,
        mock_acp_client,
        sample_agent,
    ):
        """A crash after preclaim does not leave an unrecoverable ownership lock."""
        claimed = TaskEntity(
            id=str(uuid4()),
            name="abandoned-preclaim",
            status=TaskStatus.RUNNING,
            status_reason="Retrying task forwarding to ACP server",
            failure_source=TaskFailureSource.ACP_FORWARD,
            updated_at=RACE_TIMESTAMP,
        )
        repository = InMemoryTaskStatusRepository(claimed)
        task_service = make_task_service_for_status_race(mock_acp_client, repository)

        result = await task_service.forward_task_to_acp(
            agent=sample_agent,
            task=claimed,
        )

        mock_acp_client.create_task.assert_awaited_once()
        assert result.status == TaskStatus.RUNNING
        assert result.status_reason == "Task forwarded to ACP server"
        assert result.failure_source is None

    async def test_failed_forward_retry_rolls_back_only_its_claim(
        self,
        mock_acp_client,
        sample_agent,
    ):
        failed = TaskEntity(
            id=str(uuid4()),
            name="retry-rollback",
            status=TaskStatus.FAILED,
            status_reason="Initial connection failure",
            failure_source=TaskFailureSource.ACP_FORWARD,
            updated_at=RACE_TIMESTAMP,
        )
        repository = InMemoryTaskStatusRepository(failed)
        task_service = make_task_service_for_status_race(mock_acp_client, repository)
        mock_acp_client.create_task.side_effect = RuntimeError("Still unavailable")

        with pytest.raises(RuntimeError, match="Still unavailable"):
            await task_service.forward_task_to_acp(
                agent=sample_agent,
                task=failed,
            )

        assert repository.task.status == TaskStatus.FAILED
        assert repository.task.status_reason == "Still unavailable"
        assert repository.task.failure_source == TaskFailureSource.ACP_FORWARD

    async def test_workflow_failure_wins_before_failed_retry_claim(
        self,
        mock_acp_client,
        sample_agent,
    ):
        """A workflow ownership write prevents a stale retry from reviving FAILED."""
        failed = TaskEntity(
            id=str(uuid4()),
            name="workflow-failure-wins-claim-race",
            status=TaskStatus.FAILED,
            status_reason="ACP response lost",
            failure_source=TaskFailureSource.ACP_FORWARD,
            updated_at=RACE_TIMESTAMP,
        )
        repository = InMemoryTaskStatusRepository(failed)

        async def claim_after_workflow_failure(_task_id):
            repository.claim_requests += 1
            repository.task = repository.task.model_copy(
                update={
                    "status_reason": "Workflow cleanup failed",
                    "failure_source": None,
                    "updated_at": RACE_TIMESTAMP + timedelta(microseconds=1),
                }
            )
            return None

        repository.claim_acp_forward = claim_after_workflow_failure
        task_service = make_task_service_for_status_race(mock_acp_client, repository)

        result = await task_service.forward_task_to_acp(
            agent=sample_agent,
            task=failed,
        )

        assert result.status == TaskStatus.FAILED
        assert result.status_reason == "Workflow cleanup failed"
        assert result.failure_source is None
        assert repository.claim_requests == 1
        mock_acp_client.create_task.assert_not_awaited()

    async def test_forward_task_to_acp_error_preserves_concurrent_completion(
        self,
        mock_acp_client,
        sample_agent,
    ):
        """A late forward error must not replace a concurrent terminal state."""
        task = TaskEntity(
            id=str(uuid4()),
            name="concurrently-completed-task",
            status=TaskStatus.RUNNING,
            status_reason="Task is running",
            updated_at=RACE_TIMESTAMP,
        )
        repository = InMemoryTaskStatusRepository(task)
        task_service = make_task_service_for_status_race(mock_acp_client, repository)

        async def complete_then_fail(**_kwargs):
            repository.task = repository.task.model_copy(
                update={
                    "status": TaskStatus.COMPLETED,
                    "status_reason": "Task completed",
                    "failure_source": None,
                    "updated_at": RACE_TIMESTAMP + timedelta(microseconds=1),
                }
            )
            raise RuntimeError("ACP response was lost")

        mock_acp_client.create_task.side_effect = complete_then_fail

        with pytest.raises(RuntimeError, match="ACP response was lost"):
            await task_service.forward_task_to_acp(agent=sample_agent, task=task)

        assert repository.task.status == TaskStatus.COMPLETED
        assert repository.task.status_reason == "Task completed"

    async def test_forward_task_to_acp_error_fails_interrupted_task(
        self,
        mock_acp_client,
        sample_agent,
    ):
        """A forward error can still fail an interrupted non-terminal task."""
        task = TaskEntity(
            id=str(uuid4()),
            name="interrupted-forward",
            status=TaskStatus.INTERRUPTED,
            status_reason="Task interrupted",
            updated_at=RACE_TIMESTAMP,
        )
        repository = InMemoryTaskStatusRepository(task)
        task_service = make_task_service_for_status_race(mock_acp_client, repository)
        mock_acp_client.create_task.side_effect = RuntimeError("ACP unavailable")

        with pytest.raises(RuntimeError, match="ACP unavailable"):
            await task_service.forward_task_to_acp(agent=sample_agent, task=task)

        assert repository.task.status == TaskStatus.FAILED
        assert repository.task.status_reason == "ACP unavailable"
        assert repository.claim_requests == 1
        assert repository.transition_requests == [TaskStatus.RUNNING]

    async def test_forward_task_to_acp_recovery_returns_concurrent_terminal_state(
        self,
        mock_acp_client,
        sample_agent,
    ):
        """A lost FAILED recovery race returns the current terminal task."""
        failed = TaskEntity(
            id=str(uuid4()),
            name="concurrently-reconciled-task",
            status=TaskStatus.FAILED,
            status_reason="Initial forward failed",
            failure_source=TaskFailureSource.ACP_FORWARD,
            updated_at=RACE_TIMESTAMP,
        )
        repository = InMemoryTaskStatusRepository(failed)
        task_service = make_task_service_for_status_race(mock_acp_client, repository)

        async def complete_before_returning(**_kwargs):
            repository.task = repository.task.model_copy(
                update={
                    "status": TaskStatus.COMPLETED,
                    "status_reason": "Task completed",
                    "updated_at": RACE_TIMESTAMP + timedelta(microseconds=1),
                }
            )

        mock_acp_client.create_task.side_effect = complete_before_returning

        result = await task_service.forward_task_to_acp(agent=sample_agent, task=failed)

        assert result.status == TaskStatus.COMPLETED
        assert result.status_reason == "Task completed"
        assert repository.task.status == TaskStatus.COMPLETED
        assert repository.task.status_reason == "Task completed"
        assert repository.current_reads == 1

    async def test_failed_retry_error_preserves_concurrently_recovered_task(
        self,
        mock_acp_client,
        sample_agent,
    ):
        """A losing FAILED retry cannot fail a task recovered by another retry."""
        failed = TaskEntity(
            id=str(uuid4()),
            name="concurrent-forward-retries",
            status=TaskStatus.FAILED,
            status_reason="Initial forward failed",
            failure_source=TaskFailureSource.ACP_FORWARD,
            updated_at=RACE_TIMESTAMP,
        )
        repository = InMemoryTaskStatusRepository(failed)
        task_service = make_task_service_for_status_race(mock_acp_client, repository)

        async def recover_then_fail(**_kwargs):
            repository.task = repository.task.model_copy(
                update={
                    "status": TaskStatus.RUNNING,
                    "status_reason": "Task forwarded by another request",
                    "failure_source": None,
                    "updated_at": RACE_TIMESTAMP + timedelta(microseconds=2),
                }
            )
            raise RuntimeError("Duplicate forward rejected")

        mock_acp_client.create_task.side_effect = recover_then_fail

        with pytest.raises(RuntimeError, match="Duplicate forward rejected"):
            await task_service.forward_task_to_acp(agent=sample_agent, task=failed)

        assert repository.task.status == TaskStatus.RUNNING
        assert repository.task.status_reason == "Task forwarded by another request"

    async def test_forward_error_survives_unrelated_metadata_update(
        self,
        mock_acp_client,
        sample_agent,
    ):
        """Metadata writes do not invalidate the ACP ownership marker."""
        task = TaskEntity(
            id=str(uuid4()),
            name="metadata-race",
            status=TaskStatus.RUNNING,
            status_reason="Task created",
            updated_at=RACE_TIMESTAMP,
        )
        repository = InMemoryTaskStatusRepository(task)
        task_service = make_task_service_for_status_race(mock_acp_client, repository)

        async def update_metadata_then_fail(**_kwargs):
            await repository.replace_metadata(task.id, {"source": "scheduler"})
            raise RuntimeError("ACP unavailable")

        mock_acp_client.create_task.side_effect = update_metadata_then_fail

        with pytest.raises(RuntimeError, match="ACP unavailable"):
            await task_service.forward_task_to_acp(agent=sample_agent, task=task)

        assert repository.task.status == TaskStatus.FAILED
        assert repository.task.status_reason == "ACP unavailable"
        assert repository.task.failure_source == TaskFailureSource.ACP_FORWARD
        assert repository.task.task_metadata == {"source": "scheduler"}

    async def test_successful_forward_wins_against_same_snapshot_error(
        self,
        mock_acp_client,
        sample_agent,
    ):
        """A recorded success makes a later error from the same snapshot stale."""
        task = TaskEntity(
            id=str(uuid4()),
            name="success-wins",
            status=TaskStatus.RUNNING,
            status_reason="Task created",
            updated_at=RACE_TIMESTAMP,
        )
        repository = InMemoryTaskStatusRepository(task)
        task_service = make_task_service_for_status_race(mock_acp_client, repository)
        both_started = asyncio.Event()
        release_success = asyncio.Event()
        release_error = asyncio.Event()
        started = 0

        async def controlled_forward(**kwargs):
            nonlocal started
            started += 1
            if started == 2:
                both_started.set()
            if kwargs["params"]["outcome"] == "success":
                await release_success.wait()
                return None
            await release_error.wait()
            raise RuntimeError("late forward error")

        mock_acp_client.create_task.side_effect = controlled_forward
        success_call = asyncio.create_task(
            task_service.forward_task_to_acp(
                agent=sample_agent,
                task=task,
                task_params={"outcome": "success"},
            )
        )
        error_call = asyncio.create_task(
            task_service.forward_task_to_acp(
                agent=sample_agent,
                task=task,
                task_params={"outcome": "error"},
            )
        )

        await both_started.wait()
        release_success.set()
        successful = await success_call
        assert successful.status == TaskStatus.RUNNING
        assert successful.status_reason == "Task forwarded to ACP server"

        release_error.set()
        with pytest.raises(RuntimeError, match="late forward error"):
            await error_call

        assert repository.task.status == TaskStatus.RUNNING
        assert repository.task.status_reason == "Task forwarded to ACP server"
        assert repository.current_reads == 0

    async def test_forward_success_wins_after_concurrent_error(
        self,
        mock_acp_client,
        sample_agent,
    ):
        """An accepted ACP call supersedes another forward's transport error."""
        task = TaskEntity(
            id=str(uuid4()),
            name="error-wins",
            status=TaskStatus.RUNNING,
            status_reason="Task created",
            updated_at=RACE_TIMESTAMP,
        )
        repository = InMemoryTaskStatusRepository(task)
        task_service = make_task_service_for_status_race(mock_acp_client, repository)
        both_started = asyncio.Event()
        release_success = asyncio.Event()
        release_error = asyncio.Event()
        started = 0

        async def controlled_forward(**kwargs):
            nonlocal started
            started += 1
            if started == 2:
                both_started.set()
            if kwargs["params"]["outcome"] == "success":
                await release_success.wait()
                return None
            await release_error.wait()
            raise RuntimeError("first forward error")

        mock_acp_client.create_task.side_effect = controlled_forward
        error_call = asyncio.create_task(
            task_service.forward_task_to_acp(
                agent=sample_agent,
                task=task,
                task_params={"outcome": "error"},
            )
        )
        success_call = asyncio.create_task(
            task_service.forward_task_to_acp(
                agent=sample_agent,
                task=task,
                task_params={"outcome": "success"},
            )
        )

        await both_started.wait()
        release_error.set()
        with pytest.raises(RuntimeError, match="first forward error"):
            await error_call

        release_success.set()
        result = await success_call

        assert result.status == TaskStatus.RUNNING
        assert result.status_reason == "Task forwarded to ACP server"
        assert repository.task.status == TaskStatus.RUNNING
        assert repository.task.status_reason == "Task forwarded to ACP server"
        assert repository.task.failure_source is None
        assert repository.current_reads == 0

    async def test_forward_success_does_not_require_row_version(
        self,
        mock_acp_client,
        sample_agent,
    ):
        """ACP ownership is independent of unrelated row-version timestamps."""
        task = TaskEntity(
            id=str(uuid4()),
            name="unversioned-forward",
            status=TaskStatus.RUNNING,
            status_reason="Task created",
        )
        repository = InMemoryTaskStatusRepository(task)
        task_service = make_task_service_for_status_race(mock_acp_client, repository)
        mock_acp_client.create_task.return_value = None

        result = await task_service.forward_task_to_acp(agent=sample_agent, task=task)

        assert result.status == TaskStatus.RUNNING
        assert result.status_reason == "Task forwarded to ACP server"
        assert result.failure_source is None
        assert repository.claim_requests == 1
        assert repository.transition_requests == [
            (TaskStatus.RUNNING, TaskStatus.FAILED)
        ]
        assert repository.current_reads == 0

    async def test_forward_task_to_acp_success_confirms_healthy_status(
        self,
        task_service,
        mock_acp_client,
        task_repository,
        agent_repository,
        sample_agent,
    ):
        """A successful forward records a versioned RUNNING confirmation."""
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="healthy-task"
        )
        mock_acp_client.create_task.return_value = None

        result = await task_service.forward_task_to_acp(agent=sample_agent, task=task)

        assert result.id == task.id
        assert result.status == TaskStatus.RUNNING
        assert result.status_reason == "Task forwarded to ACP server"

    async def test_get_task_by_id(
        self, task_service, task_repository, agent_repository, sample_agent
    ):
        """Test getting task by ID"""
        # Given - Create a real task in the database
        import uuid

        unique_task_name = f"test-task-{uuid.uuid4().hex[:8]}"
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name=unique_task_name
        )
        task_id = created_task.id

        # When
        result = await task_service.get_task(id=task_id)

        # Then
        assert result is not None
        assert result.id == task_id
        assert result.name == unique_task_name

    async def test_get_task_by_name(
        self, task_service, task_repository, agent_repository, sample_agent
    ):
        """Test getting task by name"""
        # Given - Create a real task in the database
        await create_or_get_agent(agent_repository, sample_agent)
        task_name = "test-task-by-name"
        created_task = await task_service.create_task(
            agent=sample_agent, task_name=task_name
        )

        # When
        result = await task_service.get_task(name=task_name)

        # Then
        assert result is not None
        assert result.id == created_task.id
        assert result.name == task_name

    async def test_update_task(
        self, task_service, task_repository, agent_repository, sample_agent
    ):
        """Test task update"""
        # Given - Create a real task in the database
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="original-task"
        )

        # Modify the task
        created_task.name = "updated-task"
        created_task.status = TaskStatus.COMPLETED

        # When
        result = await task_service.update_task(created_task)

        # Then
        assert result is not None
        assert result.id == created_task.id
        assert result.name == "updated-task"
        assert result.status == TaskStatus.COMPLETED

    async def test_replace_task_params_preserves_concurrent_terminal_status(
        self,
        task_service,
        agent_repository,
        sample_agent,
        redis_stream_repository,
    ):
        """Param replacement preserves a concurrent status and emits its state."""
        await create_or_get_agent(agent_repository, sample_agent)
        stale_task = await task_service.create_task(
            agent=sample_agent,
            task_name="replace-params-task",
            task_params={"keep": "old", "remove": True},
        )
        completed_task = await task_service.transition_task_status(
            task_id=stale_task.id,
            expected_status=TaskStatus.RUNNING,
            new_status=TaskStatus.COMPLETED,
            status_reason="Task completed",
        )
        assert completed_task is not None
        assert stale_task.status == TaskStatus.RUNNING
        redis_stream_repository.send_data = AsyncMock()

        result = await task_service.replace_task_params(stale_task.id, {"keep": "new"})

        assert result is not None
        assert result.status == TaskStatus.COMPLETED
        assert result.status_reason == "Task completed"
        assert result.params == {"keep": "new"}
        assert "remove" not in result.params
        persisted = await task_service.get_task(id=stale_task.id)
        assert persisted.status == TaskStatus.COMPLETED
        assert persisted.params == {"keep": "new"}

        redis_stream_repository.send_data.assert_awaited_once()
        topic, event = redis_stream_repository.send_data.await_args.args
        assert topic == f"task:{stale_task.id}"
        assert event["type"] == "task_updated"
        assert event["task"]["status"] == TaskStatus.COMPLETED
        assert event["task"]["params"] == {"keep": "new"}

    async def test_delete_task(
        self, task_service, task_repository, agent_repository, sample_agent
    ):
        """Test task deletion with foreign key constraint protection"""
        # Given - Create a real task in the database
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="task-to-delete"
        )
        task_id = created_task.id

        # When/Then - Attempt to delete should be prevented by foreign key constraints
        # This validates that our referential integrity is working properly
        from src.domain.exceptions import ServiceError

        with pytest.raises(ServiceError) as exc_info:
            await task_service.delete_task(id=task_id)

        # Should mention foreign key constraint violation
        assert "constraint violation" in str(exc_info.value)
        assert "task_agents" in str(exc_info.value) or "foreign key" in str(
            exc_info.value
        )

        # Task should still exist since deletion was prevented
        existing_task = await task_service.get_task(id=task_id)
        assert existing_task.id == task_id

    async def test_delete_task_with_cleanup(
        self, task_service, task_repository, agent_repository, sample_agent
    ):
        """Test successful task deletion after cleaning up related records"""
        # Given - Create a real task in the database
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="task-to-delete-clean"
        )
        task_id = created_task.id

        # When - Manually clean up related records first (simulating proper cascading delete)
        async with task_repository.start_async_db_session(True) as session:
            # Delete from task_agents and agent_task_tracker tables first
            from sqlalchemy import delete
            from src.adapters.orm import AgentTaskTrackerORM, TaskAgentORM

            # Clean up agent_task_tracker records
            await session.execute(
                delete(AgentTaskTrackerORM).where(
                    AgentTaskTrackerORM.task_id == task_id
                )
            )

            # Clean up task_agents records
            await session.execute(
                delete(TaskAgentORM).where(TaskAgentORM.task_id == task_id)
            )

            await session.commit()

        # Now deletion should succeed
        result = await task_service.delete_task(id=task_id)

        # Then
        assert result is None

        # Verify task is deleted by expecting ItemDoesNotExist when trying to get it
        from src.adapters.crud_store.exceptions import ItemDoesNotExist

        with pytest.raises(ItemDoesNotExist):
            await task_service.get_task(id=task_id)

    async def test_list_tasks(
        self, task_service, task_repository, agent_repository, sample_agent
    ):
        """Test listing all tasks"""
        # Given - Create multiple real tasks in the database
        import uuid

        test_uuid = uuid.uuid4().hex[:8]
        await create_or_get_agent(agent_repository, sample_agent)
        created_tasks = []
        for i in range(3):
            task = await task_service.create_task(
                agent=sample_agent, task_name=f"test-task-{test_uuid}-{i}"
            )
            created_tasks.append(task)

        # When
        result = await task_service.list_tasks(limit=100, page_number=1)

        # Then
        assert len(result) >= 3  # At least the tasks we created
        task_ids = [task.id for task in result]
        for created_task in created_tasks:
            assert created_task.id in task_ids

    async def test_send_message(
        self,
        task_service,
        mock_acp_client,
        sample_agent,
        sample_task,
        sample_message_content,
    ):
        """Test sending message to task"""
        # Given
        acp_url = "http://test-acp.example.com"
        mock_acp_client.send_message.return_value = sample_message_content

        # When
        result = await task_service.send_message(
            agent=sample_agent,
            task=sample_task,
            content=sample_message_content,
            acp_url=acp_url,
        )

        # Then
        assert result == sample_message_content
        mock_acp_client.send_message.assert_called_once_with(
            agent=sample_agent,
            task=sample_task,
            content=sample_message_content,
            acp_url=acp_url,
        )

    #
    async def test_send_message_stream(
        self,
        task_service,
        mock_acp_client,
        sample_agent,
        sample_task,
        sample_message_content,
    ):
        """Test streaming message to task"""
        # Given
        acp_url = "http://test-acp.example.com"
        mock_updates = [
            StreamTaskMessageDelta(
                type=TaskMessageUpdateType.DELTA,
                delta=TextDelta(type=DeltaType.TEXT, text_delta="Hello"),
            ),
            StreamTaskMessageDelta(
                type=TaskMessageUpdateType.DELTA,
                delta=TextDelta(type=DeltaType.TEXT, text_delta=" world!"),
            ),
        ]

        async def mock_stream_method(*args, **kwargs):
            for update in mock_updates:
                yield update

        # Replace the entire method with our async generator
        mock_acp_client.send_message_stream = mock_stream_method

        # When
        updates = []
        async for update in task_service.send_message_stream(
            agent=sample_agent,
            task=sample_task,
            content=sample_message_content,
            acp_url=acp_url,
        ):
            updates.append(update)

        # Then
        assert len(updates) == 2
        for update in updates:
            print("ASDF ASDF ASDF:")
            print(update)

        assert updates[0].type == TaskMessageUpdateType.DELTA
        assert updates[0].delta.root.text_delta == "Hello"
        assert updates[1].type == TaskMessageUpdateType.DELTA
        assert updates[1].delta.root.text_delta == " world!"
        # Note: We can't assert call count since we replaced the mock with a real function

    async def test_cancel_task(
        self,
        task_service,
        mock_acp_client,
        task_repository,
        agent_repository,
        sample_agent,
    ):
        """Test task cancellation"""
        # Given - Create a real task first
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="task-to-cancel"
        )
        acp_url = "http://test-acp.example.com"

        # When
        result = await task_service.cancel_task(
            agent=sample_agent, task=created_task, acp_url=acp_url
        )

        # Then
        assert result.status == TaskStatus.CANCELED
        assert result.status_reason == "Task canceled by user"

        # Verify ACP client was called to cancel the task
        mock_acp_client.cancel_task.assert_called_once_with(
            agent=sample_agent, task=created_task, acp_url=acp_url
        )

        # Verify task status is updated in the database
        updated_task = await task_service.get_task(id=created_task.id)
        assert updated_task.status == TaskStatus.CANCELED
        assert updated_task.status_reason == "Task canceled by user"

    async def test_cancel_task_replaces_acp_forward_failure(
        self,
        task_service,
        mock_acp_client,
        agent_repository,
        sample_agent,
    ):
        """A healthy workflow can be canceled after its create response is lost."""
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent,
            task_name="cancel-after-lost-create-response",
        )
        mock_acp_client.create_task.side_effect = RuntimeError("response lost")
        with pytest.raises(RuntimeError, match="response lost"):
            await task_service.forward_task_to_acp(agent=sample_agent, task=task)

        failed = await task_service.get_current_task(id=task.id)
        assert failed.status == TaskStatus.FAILED
        assert failed.failure_source == TaskFailureSource.ACP_FORWARD

        mock_acp_client.cancel_task.reset_mock()
        canceled = await task_service.cancel_task(
            agent=sample_agent,
            task=failed,
            acp_url=sample_agent.acp_url,
        )

        assert canceled.status == TaskStatus.CANCELED
        assert canceled.failure_source is None
        mock_acp_client.cancel_task.assert_awaited_once()

    async def test_create_event_and_forward_to_acp(
        self,
        task_service,
        mock_acp_client,
        event_repository,
        agent_repository,
        sample_agent,
        sample_message_content,
    ):
        """Test event creation and ACP forwarding"""
        # Given - Create real agent and task first
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="task-for-event"
        )
        acp_url = "http://test-acp.example.com"

        # When
        result = await task_service.create_event_and_forward_to_acp(
            agent=sample_agent,
            task=created_task,
            acp_url=acp_url,
            content=sample_message_content,
        )

        # Then
        assert result is not None
        assert result.id is not None
        assert result.task_id == created_task.id
        assert result.agent_id == sample_agent.id
        # Verify content was stored (checking key properties instead of exact equality)
        assert result.content is not None
        if hasattr(result.content, "content"):
            assert result.content.content == sample_message_content.content

        # Verify ACP client was called to send the event
        mock_acp_client.send_event.assert_called_once_with(
            agent=sample_agent,
            event=result,  # Use the actual created event
            task=created_task,
            acp_url=acp_url,
            request_headers=None,
        )

    async def test_create_event_and_forward_to_acp_with_headers(
        self,
        task_service,
        mock_acp_client,
        event_repository,
        agent_repository,
        sample_agent,
        sample_message_content,
    ):
        """Test event creation and ACP forwarding with request headers"""
        # Given - Create real agent and task first
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="task-for-event-with-headers"
        )
        acp_url = "http://test-acp.example.com"
        request_headers = {
            "user-agent": "integration-test",
            "x-custom-header": "custom-value",
        }

        # When
        result = await task_service.create_event_and_forward_to_acp(
            agent=sample_agent,
            task=created_task,
            acp_url=acp_url,
            content=sample_message_content,
            request_headers=request_headers,
        )

        # Then
        assert result is not None
        assert result.id is not None
        assert result.task_id == created_task.id
        assert result.agent_id == sample_agent.id
        assert result.content is not None

        # Verify ACP client was called with request_headers
        mock_acp_client.send_event.assert_called_once_with(
            agent=sample_agent,
            event=result,
            task=created_task,
            acp_url=acp_url,
            request_headers=request_headers,
        )

    async def test_create_task_with_task_metadata(
        self, task_service, agent_repository, sample_agent
    ):
        """Test task creation with task_metadata through service layer"""
        # Given - Persist the agent first to satisfy foreign key constraints
        await create_or_get_agent(agent_repository, sample_agent)
        task_metadata = {
            "workflow": {
                "stage": "initial",
                "priority": "high",
                "owner": {
                    "name": "service-test-user",
                    "department": "engineering",
                    "permissions": ["read", "write", "execute"],
                },
            },
            "configuration": {
                "version": "2.1.0",
                "environment": "test",
                "feature_flags": {
                    "enable_logging": True,
                    "debug_mode": False,
                    "experimental_feature": True,
                },
                "thresholds": {
                    "timeout": 5000,
                    "max_retries": 3,
                    "memory_limit": 512.5,
                },
            },
            "tags": ["service-layer", "metadata-test", "unit-test"],
            "custom_fields": {
                "external_references": [
                    {"system": "jira", "id": "PROJ-123"},
                    {"system": "slack", "channel": "#engineering"},
                ],
                "compliance_required": True,
                "estimated_completion": "2024-01-15T10:00:00Z",
            },
        }

        # When
        result = await task_service.create_task(
            agent=sample_agent,
            task_name="service-task-with-metadata",
            task_params={"param1": "value1"},  # Also test with params
        )

        # Manually set task_metadata since create_task doesn't have that parameter yet
        result.task_metadata = task_metadata
        updated_result = await task_service.update_task(result)

        # Then - Service correctly passes task_metadata to repository
        assert updated_result is not None
        assert updated_result.id is not None
        assert updated_result.name == "service-task-with-metadata"
        assert updated_result.task_metadata == task_metadata
        assert updated_result.params == {"param1": "value1"}  # Verify params still work

        # Verify task_metadata structure is preserved
        assert updated_result.task_metadata["workflow"]["stage"] == "initial"
        assert updated_result.task_metadata["configuration"]["version"] == "2.1.0"
        assert updated_result.task_metadata["tags"] == [
            "service-layer",
            "metadata-test",
            "unit-test",
        ]

    async def test_create_task_with_null_task_metadata(
        self, task_service, agent_repository, sample_agent
    ):
        """Test task creation with task_metadata=None through service layer"""
        # Given - Persist the agent first to satisfy foreign key constraints
        await create_or_get_agent(agent_repository, sample_agent)

        # When
        result = await task_service.create_task(
            agent=sample_agent, task_name="service-task-null-metadata"
        )

        # Set task_metadata to None explicitly
        result.task_metadata = None
        updated_result = await task_service.update_task(result)

        # Then - Service handles null task_metadata correctly
        assert updated_result is not None
        assert updated_result.id is not None
        assert updated_result.name == "service-task-null-metadata"
        assert updated_result.task_metadata is None

        # Verify retrieved task has null task_metadata
        retrieved_task = await task_service.get_task(id=updated_result.id)
        assert retrieved_task.task_metadata is None

    async def test_update_task_with_task_metadata_changes(
        self, task_service, agent_repository, sample_agent, redis_stream_repository
    ):
        """Test updating existing task's task_metadata"""
        # Given - Create a task first
        await create_or_get_agent(agent_repository, sample_agent)
        created_task = await task_service.create_task(
            agent=sample_agent, task_name="task-for-metadata-update"
        )

        # Set initial task_metadata
        initial_metadata = {
            "version": "1.0.0",
            "status": "initial",
            "config": {"debug": False},
        }
        created_task.task_metadata = initial_metadata
        await task_service.update_task(created_task)

        # When - Modify task_metadata and call update_task
        updated_metadata = {
            "version": "2.0.0",
            "status": "updated",
            "config": {"debug": True, "verbose": True},
            "new_field": "added_during_update",
            "metrics": {"update_count": 1, "last_modified_by": "test_service"},
        }
        created_task.task_metadata = updated_metadata

        # Mock the stream repository to verify stream event is published
        redis_stream_repository.send_data = AsyncMock()

        result = await task_service.update_task(created_task)

        # Then - Verify updated task_metadata persists
        assert result.task_metadata == updated_metadata
        assert result.task_metadata["version"] == "2.0.0"
        assert result.task_metadata["status"] == "updated"
        assert result.task_metadata["new_field"] == "added_during_update"

        # Verify task_metadata persists in database
        retrieved_task = await task_service.get_task(id=created_task.id)
        assert retrieved_task.task_metadata == updated_metadata

        # Verify stream event is published
        redis_stream_repository.send_data.assert_called_once()
        call_args = redis_stream_repository.send_data.call_args
        assert call_args[0][0] == f"task:{created_task.id}"  # topic
        event_data = call_args[0][1]  # data
        assert event_data["type"] == "task_updated"
        assert event_data["task"]["task_metadata"] == updated_metadata

    async def test_get_task_preserves_task_metadata(
        self, task_service, agent_repository, sample_agent
    ):
        """Test retrieving task by ID/name preserves task_metadata"""
        # Given - Create task with task_metadata
        await create_or_get_agent(agent_repository, sample_agent)
        task_metadata = {
            "retrieval_test": {
                "data_type": "complex",
                "nested_structure": {
                    "level_1": {
                        "level_2": ["array", "of", "strings"],
                        "boolean_field": True,
                        "numeric_field": 42.7,
                    }
                },
            },
            "preservation_check": {
                "created_at": "2024-01-01T00:00:00Z",
                "flags": [True, False, None],
                "null_value": None,
            },
        }

        created_task = await task_service.create_task(
            agent=sample_agent, task_name="task-metadata-preservation"
        )
        created_task.task_metadata = task_metadata
        await task_service.update_task(created_task)

        # When & Then - Retrieve by ID and verify task_metadata
        retrieved_by_id = await task_service.get_task(id=created_task.id)
        assert retrieved_by_id.task_metadata == task_metadata
        assert retrieved_by_id.task_metadata["retrieval_test"]["data_type"] == "complex"
        assert retrieved_by_id.task_metadata["preservation_check"]["null_value"] is None

        # When & Then - Retrieve by name and verify task_metadata
        retrieved_by_name = await task_service.get_task(
            name="task-metadata-preservation"
        )
        assert retrieved_by_name.task_metadata == task_metadata
        assert retrieved_by_name.id == created_task.id
        assert (
            retrieved_by_name.task_metadata["retrieval_test"]["nested_structure"][
                "level_1"
            ]["numeric_field"]
            == 42.7
        )

    async def test_task_metadata_retrieval_after_creation(
        self, task_service, agent_repository, sample_agent
    ):
        """Test end-to-end task creation and retrieval with complex task_metadata structure"""
        # Given - Create agent
        await create_or_get_agent(agent_repository, sample_agent)

        # Complex task_metadata with various data types
        complex_metadata = {
            "application": {
                "name": "TaskMetadataService",
                "version": "1.0.0",
                "environment": "test",
                "components": [
                    {
                        "name": "api_gateway",
                        "version": "2.1.3",
                        "enabled": True,
                        "config": {"port": 8080, "timeout": 30.5, "ssl_enabled": False},
                    },
                    {
                        "name": "database",
                        "version": "13.2",
                        "enabled": True,
                        "config": {
                            "host": "localhost",
                            "port": 5432,
                            "connection_pool_size": 10,
                        },
                    },
                ],
            },
            "business_rules": {
                "priority_levels": ["low", "medium", "high", "critical"],
                "approval_required": True,
                "max_duration_hours": 24,
                "cost_threshold": 1000.50,
                "allowed_users": ["admin", "developer", "qa_engineer"],
                "restrictions": {
                    "weekend_deployment": False,
                    "maintenance_window_only": True,
                    "requires_backup": True,
                },
            },
            "monitoring": {
                "alerts": {
                    "email_notifications": [
                        "admin@example.com",
                        "dev-team@example.com",
                    ],
                    "slack_channels": ["#alerts", "#development"],
                    "severity_mapping": {
                        "info": 1,
                        "warning": 2,
                        "error": 3,
                        "critical": 4,
                    },
                },
                "metrics": {
                    "collection_interval_seconds": 60,
                    "retention_days": 30,
                    "custom_metrics": ["task_duration", "error_rate", "throughput"],
                },
            },
            "compliance": {
                "gdpr_applicable": True,
                "data_classification": "internal",
                "audit_required": True,
                "retention_policy": {
                    "logs": "90_days",
                    "data": "7_years",
                    "backups": "3_years",
                },
            },
            "null_values_test": {
                "explicit_null": None,
                "empty_string": "",
                "empty_array": [],
                "empty_object": {},
            },
        }

        # When - Create task with complex task_metadata structure
        created_task = await task_service.create_task(
            agent=sample_agent,
            task_name="complex-metadata-end-to-end-test",
            task_params={"execution_mode": "test", "dry_run": True},
        )
        created_task.task_metadata = complex_metadata
        updated_task = await task_service.update_task(created_task)

        # Then - Retrieve and verify exact task_metadata match
        retrieved_task = await task_service.get_task(id=updated_task.id)
        assert retrieved_task.task_metadata == complex_metadata

        # Test with nested objects - verify deep structure preservation
        assert (
            retrieved_task.task_metadata["application"]["name"] == "TaskMetadataService"
        )
        assert len(retrieved_task.task_metadata["application"]["components"]) == 2
        assert (
            retrieved_task.task_metadata["application"]["components"][0]["config"][
                "port"
            ]
            == 8080
        )
        assert (
            retrieved_task.task_metadata["application"]["components"][1]["config"][
                "connection_pool_size"
            ]
            == 10
        )

        # Test with arrays - verify array preservation
        assert retrieved_task.task_metadata["business_rules"]["priority_levels"] == [
            "low",
            "medium",
            "high",
            "critical",
        ]
        assert len(retrieved_task.task_metadata["business_rules"]["allowed_users"]) == 3
        assert (
            "qa_engineer"
            in retrieved_task.task_metadata["business_rules"]["allowed_users"]
        )

        # Test various data types - verify type preservation
        assert isinstance(
            retrieved_task.task_metadata["business_rules"]["approval_required"], bool
        )
        assert isinstance(
            retrieved_task.task_metadata["business_rules"]["max_duration_hours"], int
        )
        assert isinstance(
            retrieved_task.task_metadata["business_rules"]["cost_threshold"], float
        )
        assert (
            retrieved_task.task_metadata["business_rules"]["cost_threshold"] == 1000.50
        )

        # Test null values and empty structures
        assert retrieved_task.task_metadata["null_values_test"]["explicit_null"] is None
        assert retrieved_task.task_metadata["null_values_test"]["empty_string"] == ""
        assert retrieved_task.task_metadata["null_values_test"]["empty_array"] == []
        assert retrieved_task.task_metadata["null_values_test"]["empty_object"] == {}

        # Verify params are still preserved alongside task_metadata
        assert retrieved_task.params == {"execution_mode": "test", "dry_run": True}
