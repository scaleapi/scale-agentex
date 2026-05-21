from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from src.api.schemas.schedules import (
    CreateScheduleRequest,
    ScheduleActionInfo,
    ScheduleListItem,
    ScheduleListResponse,
    ScheduleResponse,
    ScheduleSpecInfo,
    ScheduleState,
)
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.exceptions import ClientError
from src.domain.use_cases.schedules_use_case import SchedulesUseCase


@pytest.fixture
def mock_schedule_service():
    """Mock schedule service for testing use case"""
    mock = AsyncMock()
    mock.create_schedule = AsyncMock()
    mock.get_schedule = AsyncMock()
    mock.list_schedules = AsyncMock()
    mock.pause_schedule = AsyncMock()
    mock.unpause_schedule = AsyncMock()
    mock.trigger_schedule = AsyncMock()
    mock.delete_schedule = AsyncMock()
    return mock


@pytest.fixture
def schedules_use_case(mock_schedule_service):
    """Create SchedulesUseCase instance with mocked service"""
    return SchedulesUseCase(schedule_service=mock_schedule_service)


@pytest.fixture
def sample_agent():
    """Sample agent entity for testing"""
    return AgentEntity(
        id=str(uuid4()),
        name="test-agent",
        description="A test agent for use case testing",
        status=AgentStatus.READY,
        acp_type=ACPType.ASYNC,
        acp_url="http://test-acp.example.com",
    )


@pytest.fixture
def sample_schedule_response(sample_agent):
    """Sample schedule response for testing"""
    return ScheduleResponse(
        schedule_id=f"{sample_agent.id}--weekly-task",
        name="weekly-task",
        agent_id=sample_agent.id,
        state=ScheduleState.ACTIVE,
        action=ScheduleActionInfo(
            workflow_name="test-workflow",
            workflow_id_prefix=f"{sample_agent.id}--weekly-task-run",
            task_queue="test-queue",
            workflow_params=None,
        ),
        spec=ScheduleSpecInfo(
            cron_expressions=["0 0 * * 0"],
            intervals_seconds=[],
            start_at=None,
            end_at=None,
        ),
        num_actions_taken=5,
        num_actions_missed=0,
        next_action_times=[datetime.now(UTC) + timedelta(hours=1)],
        last_action_time=datetime.now(UTC) - timedelta(days=1),
        created_at=datetime.now(UTC) - timedelta(days=7),
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestSchedulesUseCase:
    """Test suite for SchedulesUseCase"""

    async def test_create_schedule_with_cron(
        self,
        schedules_use_case,
        mock_schedule_service,
        sample_agent,
        sample_schedule_response,
    ):
        """Test creating a schedule with cron expression"""
        # Given
        request = CreateScheduleRequest(
            name="weekly-task",
            workflow_name="test-workflow",
            task_queue="test-queue",
            cron_expression="0 0 * * 0",
        )
        mock_schedule_service.create_schedule.return_value = sample_schedule_response

        # When
        result = await schedules_use_case.create_schedule(sample_agent, request)

        # Then
        assert result is not None
        assert isinstance(result, ScheduleResponse)
        assert result.name == "weekly-task"
        assert result.state == ScheduleState.ACTIVE
        mock_schedule_service.create_schedule.assert_called_once_with(
            sample_agent, request
        )

    async def test_create_schedule_with_interval(
        self, schedules_use_case, mock_schedule_service, sample_agent
    ):
        """Test creating a schedule with interval"""
        # Given
        request = CreateScheduleRequest(
            name="interval-task",
            workflow_name="test-workflow",
            task_queue="test-queue",
            interval_seconds=3600,
        )
        expected_response = ScheduleResponse(
            schedule_id=f"{sample_agent.id}--interval-task",
            name="interval-task",
            agent_id=sample_agent.id,
            state=ScheduleState.ACTIVE,
            action=ScheduleActionInfo(
                workflow_name="test-workflow",
                workflow_id_prefix=f"{sample_agent.id}--interval-task-run",
                task_queue="test-queue",
                workflow_params=None,
            ),
            spec=ScheduleSpecInfo(
                cron_expressions=[],
                intervals_seconds=[3600],
                start_at=None,
                end_at=None,
            ),
        )
        mock_schedule_service.create_schedule.return_value = expected_response

        # When
        result = await schedules_use_case.create_schedule(sample_agent, request)

        # Then
        assert result is not None
        assert result.spec.intervals_seconds == [3600]
        mock_schedule_service.create_schedule.assert_called_once()

    async def test_create_schedule_validation_error_no_schedule_spec(
        self, schedules_use_case, sample_agent
    ):
        """Test that creating a schedule without cron or interval raises error"""
        # Given
        request = CreateScheduleRequest(
            name="invalid-task",
            workflow_name="test-workflow",
            task_queue="test-queue",
            # Neither cron_expression nor interval_seconds provided
        )

        # When/Then
        with pytest.raises(ClientError) as exc_info:
            await schedules_use_case.create_schedule(sample_agent, request)

        assert "Either cron_expression or interval_seconds must be provided" in str(
            exc_info.value
        )

    async def test_create_schedule_with_both_cron_and_interval(
        self, schedules_use_case, mock_schedule_service, sample_agent
    ):
        """Test creating a schedule with both cron and interval (should succeed)"""
        # Given - having both is valid, cron takes precedence
        request = CreateScheduleRequest(
            name="combined-task",
            workflow_name="test-workflow",
            task_queue="test-queue",
            cron_expression="0 0 * * *",
            interval_seconds=3600,
        )
        expected_response = ScheduleResponse(
            schedule_id=f"{sample_agent.id}--combined-task",
            name="combined-task",
            agent_id=sample_agent.id,
            state=ScheduleState.ACTIVE,
            action=ScheduleActionInfo(
                workflow_name="test-workflow",
                workflow_id_prefix=f"{sample_agent.id}--combined-task-run",
                task_queue="test-queue",
                workflow_params=None,
            ),
            spec=ScheduleSpecInfo(
                cron_expressions=["0 0 * * *"],
                intervals_seconds=[3600],
                start_at=None,
                end_at=None,
            ),
        )
        mock_schedule_service.create_schedule.return_value = expected_response

        # When
        result = await schedules_use_case.create_schedule(sample_agent, request)

        # Then
        assert result is not None
        mock_schedule_service.create_schedule.assert_called_once()

    async def test_create_schedule_with_workflow_params(
        self, schedules_use_case, mock_schedule_service, sample_agent
    ):
        """Test creating a schedule with workflow parameters"""
        # Given
        workflow_params = {
            "input_data": "test",
            "config": {"timeout": 300, "retries": 3},
        }
        request = CreateScheduleRequest(
            name="params-task",
            workflow_name="test-workflow",
            task_queue="test-queue",
            cron_expression="0 0 * * *",
            workflow_params=workflow_params,
        )
        expected_response = ScheduleResponse(
            schedule_id=f"{sample_agent.id}--params-task",
            name="params-task",
            agent_id=sample_agent.id,
            state=ScheduleState.ACTIVE,
            action=ScheduleActionInfo(
                workflow_name="test-workflow",
                workflow_id_prefix=f"{sample_agent.id}--params-task-run",
                task_queue="test-queue",
                workflow_params=[workflow_params],
            ),
            spec=ScheduleSpecInfo(
                cron_expressions=["0 0 * * *"],
                intervals_seconds=[],
                start_at=None,
                end_at=None,
            ),
        )
        mock_schedule_service.create_schedule.return_value = expected_response

        # When
        result = await schedules_use_case.create_schedule(sample_agent, request)

        # Then
        assert result is not None
        assert result.action.workflow_params == [workflow_params]

    async def test_get_schedule(
        self,
        schedules_use_case,
        mock_schedule_service,
        sample_agent,
        sample_schedule_response,
    ):
        """Test getting a schedule by name"""
        # Given
        mock_schedule_service.get_schedule.return_value = sample_schedule_response

        # When
        result = await schedules_use_case.get_schedule(sample_agent.id, "weekly-task")

        # Then
        assert result is not None
        assert result.name == "weekly-task"
        assert result.agent_id == sample_agent.id
        mock_schedule_service.get_schedule.assert_called_once_with(
            sample_agent.id, "weekly-task"
        )

    async def test_list_schedules(
        self, schedules_use_case, mock_schedule_service, sample_agent
    ):
        """Test listing schedules for an agent"""
        # Given
        expected_response = ScheduleListResponse(
            schedules=[
                ScheduleListItem(
                    schedule_id=f"{sample_agent.id}--schedule-1",
                    name="schedule-1",
                    agent_id=sample_agent.id,
                    state=ScheduleState.ACTIVE,
                    workflow_name="workflow-1",
                    next_action_time=datetime.now(UTC),
                ),
                ScheduleListItem(
                    schedule_id=f"{sample_agent.id}--schedule-2",
                    name="schedule-2",
                    agent_id=sample_agent.id,
                    state=ScheduleState.PAUSED,
                    workflow_name="workflow-2",
                    next_action_time=None,
                ),
            ],
            total=2,
        )
        mock_schedule_service.list_schedules.return_value = expected_response

        # When
        result = await schedules_use_case.list_schedules(sample_agent.id)

        # Then
        assert result is not None
        assert result.total == 2
        assert len(result.schedules) == 2
        mock_schedule_service.list_schedules.assert_called_once_with(
            agent_id=sample_agent.id, page_size=100
        )

    async def test_list_schedules_with_page_size(
        self, schedules_use_case, mock_schedule_service, sample_agent
    ):
        """Test listing schedules with custom page size"""
        # Given
        expected_response = ScheduleListResponse(schedules=[], total=0)
        mock_schedule_service.list_schedules.return_value = expected_response

        # When
        result = await schedules_use_case.list_schedules(sample_agent.id, page_size=50)

        # Then
        assert result is not None
        mock_schedule_service.list_schedules.assert_called_once_with(
            agent_id=sample_agent.id, page_size=50
        )

    async def test_pause_schedule(
        self, schedules_use_case, mock_schedule_service, sample_agent
    ):
        """Test pausing a schedule"""
        # Given
        paused_response = ScheduleResponse(
            schedule_id=f"{sample_agent.id}--weekly-task",
            name="weekly-task",
            agent_id=sample_agent.id,
            state=ScheduleState.PAUSED,
            action=ScheduleActionInfo(
                workflow_name="test-workflow",
                workflow_id_prefix=f"{sample_agent.id}--weekly-task-run",
                task_queue="test-queue",
                workflow_params=None,
            ),
            spec=ScheduleSpecInfo(
                cron_expressions=["0 0 * * 0"],
                intervals_seconds=[],
                start_at=None,
                end_at=None,
            ),
        )
        mock_schedule_service.pause_schedule.return_value = paused_response

        # When
        result = await schedules_use_case.pause_schedule(
            sample_agent.id, "weekly-task", note="Maintenance window"
        )

        # Then
        assert result is not None
        assert result.state == ScheduleState.PAUSED
        mock_schedule_service.pause_schedule.assert_called_once_with(
            sample_agent.id, "weekly-task", note="Maintenance window"
        )

    async def test_pause_schedule_without_note(
        self, schedules_use_case, mock_schedule_service, sample_agent
    ):
        """Test pausing a schedule without a note"""
        # Given
        paused_response = ScheduleResponse(
            schedule_id=f"{sample_agent.id}--weekly-task",
            name="weekly-task",
            agent_id=sample_agent.id,
            state=ScheduleState.PAUSED,
            action=ScheduleActionInfo(
                workflow_name="test-workflow",
                workflow_id_prefix=f"{sample_agent.id}--weekly-task-run",
                task_queue="test-queue",
                workflow_params=None,
            ),
            spec=ScheduleSpecInfo(
                cron_expressions=["0 0 * * 0"],
                intervals_seconds=[],
                start_at=None,
                end_at=None,
            ),
        )
        mock_schedule_service.pause_schedule.return_value = paused_response

        # When
        result = await schedules_use_case.pause_schedule(sample_agent.id, "weekly-task")

        # Then
        assert result is not None
        mock_schedule_service.pause_schedule.assert_called_once_with(
            sample_agent.id, "weekly-task", note=None
        )

    async def test_unpause_schedule(
        self,
        schedules_use_case,
        mock_schedule_service,
        sample_agent,
        sample_schedule_response,
    ):
        """Test unpausing a schedule"""
        # Given
        mock_schedule_service.unpause_schedule.return_value = sample_schedule_response

        # When
        result = await schedules_use_case.unpause_schedule(
            sample_agent.id, "weekly-task", note="Maintenance complete"
        )

        # Then
        assert result is not None
        assert result.state == ScheduleState.ACTIVE
        mock_schedule_service.unpause_schedule.assert_called_once_with(
            sample_agent.id, "weekly-task", note="Maintenance complete"
        )

    async def test_unpause_schedule_without_note(
        self,
        schedules_use_case,
        mock_schedule_service,
        sample_agent,
        sample_schedule_response,
    ):
        """Test unpausing a schedule without a note"""
        # Given
        mock_schedule_service.unpause_schedule.return_value = sample_schedule_response

        # When
        result = await schedules_use_case.unpause_schedule(
            sample_agent.id, "weekly-task"
        )

        # Then
        assert result is not None
        mock_schedule_service.unpause_schedule.assert_called_once_with(
            sample_agent.id, "weekly-task", note=None
        )

    async def test_trigger_schedule(
        self,
        schedules_use_case,
        mock_schedule_service,
        sample_agent,
        sample_schedule_response,
    ):
        """Test triggering a schedule immediately"""
        # Given
        mock_schedule_service.trigger_schedule.return_value = sample_schedule_response

        # When
        result = await schedules_use_case.trigger_schedule(
            sample_agent.id, "weekly-task"
        )

        # Then
        assert result is not None
        mock_schedule_service.trigger_schedule.assert_called_once_with(
            sample_agent.id, "weekly-task"
        )

    async def test_delete_schedule(
        self, schedules_use_case, mock_schedule_service, sample_agent
    ):
        """Test deleting a schedule"""
        # Given
        mock_schedule_service.delete_schedule.return_value = None

        # When
        await schedules_use_case.delete_schedule(sample_agent.id, "weekly-task")

        # Then
        mock_schedule_service.delete_schedule.assert_called_once_with(
            sample_agent.id, "weekly-task"
        )

    async def test_create_schedule_paused(
        self, schedules_use_case, mock_schedule_service, sample_agent
    ):
        """Test creating a schedule in paused state"""
        # Given
        request = CreateScheduleRequest(
            name="paused-task",
            workflow_name="test-workflow",
            task_queue="test-queue",
            cron_expression="0 0 * * *",
            paused=True,
        )
        paused_response = ScheduleResponse(
            schedule_id=f"{sample_agent.id}--paused-task",
            name="paused-task",
            agent_id=sample_agent.id,
            state=ScheduleState.PAUSED,
            action=ScheduleActionInfo(
                workflow_name="test-workflow",
                workflow_id_prefix=f"{sample_agent.id}--paused-task-run",
                task_queue="test-queue",
                workflow_params=None,
            ),
            spec=ScheduleSpecInfo(
                cron_expressions=["0 0 * * *"],
                intervals_seconds=[],
                start_at=None,
                end_at=None,
            ),
        )
        mock_schedule_service.create_schedule.return_value = paused_response

        # When
        result = await schedules_use_case.create_schedule(sample_agent, request)

        # Then
        assert result is not None
        assert result.state == ScheduleState.PAUSED

    async def test_create_schedule_with_execution_timeout(
        self, schedules_use_case, mock_schedule_service, sample_agent
    ):
        """Test creating a schedule with execution timeout"""
        # Given
        request = CreateScheduleRequest(
            name="timeout-task",
            workflow_name="test-workflow",
            task_queue="test-queue",
            cron_expression="0 0 * * *",
            execution_timeout_seconds=7200,
        )
        expected_response = ScheduleResponse(
            schedule_id=f"{sample_agent.id}--timeout-task",
            name="timeout-task",
            agent_id=sample_agent.id,
            state=ScheduleState.ACTIVE,
            action=ScheduleActionInfo(
                workflow_name="test-workflow",
                workflow_id_prefix=f"{sample_agent.id}--timeout-task-run",
                task_queue="test-queue",
                workflow_params=None,
            ),
            spec=ScheduleSpecInfo(
                cron_expressions=["0 0 * * *"],
                intervals_seconds=[],
                start_at=None,
                end_at=None,
            ),
        )
        mock_schedule_service.create_schedule.return_value = expected_response

        # When
        result = await schedules_use_case.create_schedule(sample_agent, request)

        # Then
        assert result is not None
        # Verify the request was passed through to the service
        call_args = mock_schedule_service.create_schedule.call_args
        assert call_args[0][1].execution_timeout_seconds == 7200

    async def test_create_schedule_with_time_bounds(
        self, schedules_use_case, mock_schedule_service, sample_agent
    ):
        """Test creating a schedule with start and end times"""
        # Given
        start_at = datetime.now(UTC) + timedelta(days=1)
        end_at = datetime.now(UTC) + timedelta(days=30)
        request = CreateScheduleRequest(
            name="bounded-task",
            workflow_name="test-workflow",
            task_queue="test-queue",
            cron_expression="0 0 * * *",
            start_at=start_at,
            end_at=end_at,
        )
        expected_response = ScheduleResponse(
            schedule_id=f"{sample_agent.id}--bounded-task",
            name="bounded-task",
            agent_id=sample_agent.id,
            state=ScheduleState.ACTIVE,
            action=ScheduleActionInfo(
                workflow_name="test-workflow",
                workflow_id_prefix=f"{sample_agent.id}--bounded-task-run",
                task_queue="test-queue",
                workflow_params=None,
            ),
            spec=ScheduleSpecInfo(
                cron_expressions=["0 0 * * *"],
                intervals_seconds=[],
                start_at=start_at,
                end_at=end_at,
            ),
        )
        mock_schedule_service.create_schedule.return_value = expected_response

        # When
        result = await schedules_use_case.create_schedule(sample_agent, request)

        # Then
        assert result is not None
        assert result.spec.start_at == start_at
        assert result.spec.end_at == end_at

    async def test_list_schedules_empty(
        self, schedules_use_case, mock_schedule_service, sample_agent
    ):
        """Test listing schedules when none exist"""
        # Given
        expected_response = ScheduleListResponse(schedules=[], total=0)
        mock_schedule_service.list_schedules.return_value = expected_response

        # When
        result = await schedules_use_case.list_schedules(sample_agent.id)

        # Then
        assert result is not None
        assert result.total == 0
        assert len(result.schedules) == 0
