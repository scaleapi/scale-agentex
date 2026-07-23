"""
Unit tests for TasksUseCase - status transition logic via explicit status
methods (complete_task, fail_task, etc.) and metadata updates.
"""

from unittest.mock import AsyncMock
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

    # --- Non-terminal interrupt (RUNNING <-> INTERRUPTED) ---

    async def test_interrupt_running_task_is_non_terminal(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Interrupt transitions RUNNING -> INTERRUPTED, a non-terminal status."""
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="interrupt-test"
        )
        assert task.status == TaskStatus.RUNNING

        # When
        updated = await tasks_use_case.interrupt_task(
            id=task.id, reason="User hit stop"
        )

        # Then
        assert updated.status == TaskStatus.INTERRUPTED
        assert updated.status_reason == "User hit stop"

    async def test_interrupt_default_reason(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Interrupt without an explicit reason uses the default."""
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="interrupt-default-reason-test"
        )

        updated = await tasks_use_case.interrupt_task(id=task.id)

        assert updated.status == TaskStatus.INTERRUPTED
        assert updated.status_reason == "Task interrupted"

    async def test_interrupted_task_can_resume_to_running(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """INTERRUPTED -> RUNNING on next-turn start (resume_interrupted_task)."""
        # Given an interrupted task
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="interrupt-resume-test"
        )
        await tasks_use_case.interrupt_task(id=task.id)

        # When the next turn starts
        resumed = await task_service.resume_interrupted_task(task.id)

        # Then it is RUNNING again
        assert resumed is not None
        assert resumed.status == TaskStatus.RUNNING

    async def test_resume_non_interrupted_task_is_noop(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Resuming a task that is not INTERRUPTED must not clobber its status."""
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="interrupt-resume-noop-test"
        )
        # RUNNING (not INTERRUPTED): the compare-and-swap misses, returns None.
        resumed = await task_service.resume_interrupted_task(task.id)
        assert resumed is None

    async def test_interrupted_task_can_transition_to_terminal(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """An INTERRUPTED task is still transition-eligible: it can be canceled
        (terminal-from-INTERRUPTED) later."""
        # Given an interrupted task
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="interrupt-then-cancel-test"
        )
        interrupted = await tasks_use_case.interrupt_task(id=task.id)
        assert interrupted.status == TaskStatus.INTERRUPTED

        # When the interrupted task is canceled
        canceled = await tasks_use_case.cancel_task(
            id=task.id, reason="User canceled after interrupt"
        )

        # Then the terminal transition succeeds from INTERRUPTED
        assert canceled.status == TaskStatus.CANCELED
        assert canceled.status_reason == "User canceled after interrupt"

    async def test_interrupted_task_can_be_completed(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """terminal-from-INTERRUPTED also works for complete()."""
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="interrupt-then-complete-test"
        )
        await tasks_use_case.interrupt_task(id=task.id)

        completed = await tasks_use_case.complete_task(id=task.id, reason="done")

        assert completed.status == TaskStatus.COMPLETED

    async def test_cannot_interrupt_non_running_task(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """A task that is not RUNNING cannot be interrupted."""
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="interrupt-non-running-test"
        )
        await tasks_use_case.complete_task(id=task.id)

        with pytest.raises(ClientError, match="Only running"):
            await tasks_use_case.interrupt_task(id=task.id)

    async def test_cannot_interrupt_already_interrupted_task(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Interrupt is only valid from RUNNING; a second interrupt is rejected."""
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="interrupt-twice-test"
        )
        await tasks_use_case.interrupt_task(id=task.id)

        with pytest.raises(ClientError, match="Only running"):
            await tasks_use_case.interrupt_task(id=task.id)

    async def test_interrupt_requires_id_or_name(self, tasks_use_case):
        """Interrupt with neither id nor name raises."""
        with pytest.raises(ClientError, match="Either id or name"):
            await tasks_use_case.interrupt_task()

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
        with pytest.raises(ClientError, match="Only running"):
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
        with pytest.raises(ClientError, match="Only running"):
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
        with pytest.raises(ClientError, match="Only running"):
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
        with pytest.raises(ClientError, match="Only running"):
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
        with pytest.raises(ClientError, match="Only running"):
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

    async def test_update_metadata_and_merge_params_both_persist(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Supplying both task_metadata and merge_params must persist both fields.

        Regression: the merge previously reassigned task_entity to the merged
        result, discarding the in-memory task_metadata before the final write.
        """
        # Given
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent,
            task_name="combined-update-test",
            task_params={"model": "gpt-4"},
        )

        # When
        updated = await tasks_use_case.update_mutable_fields_on_task(
            id=task.id,
            task_metadata={"stage": "tuned"},
            merge_params={"temperature": 0.7},
        )

        # Then
        assert updated.task_metadata == {"stage": "tuned"}
        assert updated.params == {"model": "gpt-4", "temperature": 0.7}

    async def test_update_current_state(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """current_state persists and leaves status/task_metadata untouched."""
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent,
            task_name="current-state-test",
            task_metadata={"keep": "me"},
        )

        updated = await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, current_state="working"
        )

        assert updated.current_state == "working"
        assert updated.status == TaskStatus.RUNNING
        assert updated.task_metadata == {"keep": "me"}

    async def test_update_current_state_noop_when_omitted(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Omitting current_state (the UNSET default) leaves it untouched."""
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="current-state-omitted-test"
        )
        await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, current_state="set-once"
        )

        # A later metadata-only update must not clear current_state.
        updated = await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, task_metadata={"a": 1}
        )

        assert updated.current_state == "set-once"

    async def test_update_current_state_clears_on_explicit_null(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Passing current_state=None explicitly clears the label (vs omitting)."""
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="current-state-clear-test"
        )
        was_set = await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, current_state="working"
        )
        # Confirm it was actually set, so the clear below is a real transition
        # (not a null→null no-op that would pass trivially).
        assert was_set.current_state == "working"

        cleared = await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, current_state=None
        )

        assert cleared.current_state is None

    async def test_update_current_state_and_metadata_single_atomic_write(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Supplying current_state + task_metadata together persists both via a
        single atomic write (one publish), and does not clobber status."""
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="current-state-combined-test"
        )

        spy = AsyncMock(wraps=task_service.update_mutable_fields)
        task_service.update_mutable_fields = spy

        updated = await tasks_use_case.update_mutable_fields_on_task(
            id=task.id,
            task_metadata={"stage": "two"},
            current_state="working",
        )

        spy.assert_awaited_once()
        assert updated.current_state == "working"
        assert updated.task_metadata == {"stage": "two"}
        assert updated.status == TaskStatus.RUNNING

    async def test_update_current_state_does_not_clobber_concurrent_status(
        self, tasks_use_case, task_service, task_repository, agent_repository, sample_agent
    ):
        """Regression (round-one blocker): a current_state write must not revert a
        status changed concurrently. Reproduces the exact staleness the old
        whole-row-merge path needed — the use case reads the entity while RUNNING,
        the task goes COMPLETED before the write lands, and the write must keep
        COMPLETED. Fails on the old update_task/merge path (reverts to RUNNING),
        passes on the column-scoped update.
        """
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="current-state-clobber-test"
        )

        # Snapshot the entity as the use case would have read it, BEFORE the
        # concurrent transition — this is the stale read the bug wrote back.
        stale_entity = await task_service.get_task(id=task.id)
        assert stale_entity.status == TaskStatus.RUNNING

        # Another writer moves the task to a terminal status after that read.
        await task_service.transition_task_status(
            task_id=task.id,
            expected_status=TaskStatus.RUNNING,
            new_status=TaskStatus.COMPLETED,
            status_reason="done",
        )

        # Force the use case to operate on the stale (pre-transition) read.
        task_service.get_task = AsyncMock(return_value=stale_entity)

        updated = await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, current_state="late"
        )

        # The write set current_state without reverting the terminal status.
        assert updated.current_state == "late"
        assert updated.status == TaskStatus.COMPLETED
        persisted = await task_repository.get(id=task.id)
        assert persisted.status == TaskStatus.COMPLETED
        assert persisted.current_state == "late"

    async def test_update_current_state_on_deleted_task_raises(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """Updating current_state on a deleted task raises not found."""
        await create_or_get_agent(agent_repository, sample_agent)
        task = await task_service.create_task(
            agent=sample_agent, task_name="current-state-deleted-test"
        )
        await tasks_use_case.delete_task(id=task.id)

        with pytest.raises(ItemDoesNotExist):
            await tasks_use_case.update_mutable_fields_on_task(
                id=task.id, current_state="working"
            )

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


@pytest.mark.unit
@pytest.mark.asyncio
class TestTasksUseCaseListTasks:
    """Test suite for list_tasks filtering"""

    async def test_list_tasks_forwards_task_metadata_filter(
        self, tasks_use_case, task_service, agent_repository, sample_agent
    ):
        """list_tasks should forward task_metadata filter to the service/repository."""
        await create_or_get_agent(agent_repository, sample_agent)

        suffix = uuid4().hex[:8]
        matching = await task_service.create_task(
            agent=sample_agent, task_name=f"match-{suffix}"
        )
        other = await task_service.create_task(
            agent=sample_agent, task_name=f"other-{suffix}"
        )

        await tasks_use_case.update_mutable_fields_on_task(
            id=matching.id, task_metadata={"created_by_user_id": "user-a"}
        )
        await tasks_use_case.update_mutable_fields_on_task(
            id=other.id, task_metadata={"created_by_user_id": "user-b"}
        )

        results = await tasks_use_case.list_tasks(
            limit=100,
            page_number=1,
            task_metadata={"created_by_user_id": "user-a"},
        )

        result_ids = {t.id for t in results}
        assert matching.id in result_ids
        assert other.id not in result_ids
