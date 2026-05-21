from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from src.adapters.temporal.exceptions import (
    TemporalScheduleAlreadyExistsError,
    TemporalScheduleError,
    TemporalScheduleNotFoundError,
)
from src.api.schemas.schedules import (
    CreateScheduleRequest,
    ScheduleListResponse,
    ScheduleResponse,
    ScheduleState,
)
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.services.schedule_service import (
    SCHEDULE_ID_SEPARATOR,
    ScheduleService,
    build_schedule_id,
    parse_schedule_id,
)
from temporalio.client import (
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleDescription,
    ScheduleInfo,
    ScheduleIntervalSpec,
    ScheduleSpec,
)
from temporalio.client import (
    ScheduleState as TemporalScheduleState,
)


@pytest.fixture
def mock_temporal_adapter():
    """Mock Temporal adapter for testing schedule service"""
    mock = AsyncMock()
    mock.create_schedule = AsyncMock()
    mock.describe_schedule = AsyncMock()
    mock.list_schedules = AsyncMock()
    mock.pause_schedule = AsyncMock()
    mock.unpause_schedule = AsyncMock()
    mock.trigger_schedule = AsyncMock()
    mock.delete_schedule = AsyncMock()
    return mock


@pytest.fixture
def schedule_service(mock_temporal_adapter):
    """Create ScheduleService instance with mocked temporal adapter"""
    return ScheduleService(temporal_adapter=mock_temporal_adapter)


@pytest.fixture
def sample_agent():
    """Sample agent entity for testing"""
    return AgentEntity(
        id=str(uuid4()),
        name="test-agent",
        description="A test agent for schedule testing",
        status=AgentStatus.READY,
        acp_type=ACPType.ASYNC,
        acp_url="http://test-acp.example.com",
    )


@pytest.fixture
def sample_create_schedule_request():
    """Sample schedule creation request"""
    return CreateScheduleRequest(
        name="weekly-task",
        workflow_name="test-workflow",
        task_queue="test-queue",
        cron_expression="0 0 * * 0",
        workflow_params={"key": "value"},
    )


@pytest.fixture
def sample_create_schedule_request_interval():
    """Sample schedule creation request with interval"""
    return CreateScheduleRequest(
        name="interval-task",
        workflow_name="test-workflow",
        task_queue="test-queue",
        interval_seconds=3600,
        workflow_params={"key": "value"},
    )


def create_mock_schedule_description(
    schedule_id: str,
    workflow_name: str = "test-workflow",
    task_queue: str = "test-queue",
    paused: bool = False,
    cron_expressions: list[str] | None = None,
    intervals: list[ScheduleIntervalSpec] | None = None,
) -> ScheduleDescription:
    """Helper to create a mock ScheduleDescription"""
    # Create mock action
    mock_action = MagicMock(spec=ScheduleActionStartWorkflow)
    mock_action.workflow = workflow_name
    mock_action.id = f"{schedule_id}-run"
    mock_action.task_queue = task_queue
    mock_action.args = None

    # Create mock spec
    mock_spec = MagicMock(spec=ScheduleSpec)
    mock_spec.cron_expressions = cron_expressions or []
    mock_spec.intervals = intervals or []
    mock_spec.start_at = None
    mock_spec.end_at = None

    # Create mock state
    mock_state = MagicMock(spec=TemporalScheduleState)
    mock_state.paused = paused

    # Create mock schedule
    mock_schedule = MagicMock(spec=Schedule)
    mock_schedule.action = mock_action
    mock_schedule.spec = mock_spec
    mock_schedule.state = mock_state

    # Create mock info
    mock_info = MagicMock(spec=ScheduleInfo)
    mock_info.num_actions = 5
    mock_info.num_actions_missed_catchup_window = 0
    mock_info.next_action_times = [datetime.now(UTC) + timedelta(hours=1)]
    mock_info.recent_actions = []
    mock_info.create_time = datetime.now(UTC)

    # Create mock description
    mock_description = MagicMock(spec=ScheduleDescription)
    mock_description.schedule = mock_schedule
    mock_description.info = mock_info

    return mock_description


@pytest.mark.unit
class TestScheduleIdHelpers:
    """Test suite for schedule ID helper functions"""

    def test_build_schedule_id(self):
        """Test building schedule ID from agent ID and schedule name"""
        agent_id = "agent-123"
        schedule_name = "weekly-task"

        result = build_schedule_id(agent_id, schedule_name)

        assert result == f"agent-123{SCHEDULE_ID_SEPARATOR}weekly-task"
        assert SCHEDULE_ID_SEPARATOR in result

    def test_parse_schedule_id(self):
        """Test parsing schedule ID into agent ID and schedule name"""
        schedule_id = f"agent-123{SCHEDULE_ID_SEPARATOR}weekly-task"

        agent_id, schedule_name = parse_schedule_id(schedule_id)

        assert agent_id == "agent-123"
        assert schedule_name == "weekly-task"

    def test_parse_schedule_id_invalid_format(self):
        """Test parsing invalid schedule ID"""
        schedule_id = "invalid-id-without-separator"

        agent_id, schedule_name = parse_schedule_id(schedule_id)

        assert agent_id == schedule_id
        assert schedule_name == ""

    def test_build_and_parse_roundtrip(self):
        """Test that build and parse are inverse operations"""
        original_agent_id = "agent-uuid-12345"
        original_schedule_name = "my-schedule"

        schedule_id = build_schedule_id(original_agent_id, original_schedule_name)
        parsed_agent_id, parsed_schedule_name = parse_schedule_id(schedule_id)

        assert parsed_agent_id == original_agent_id
        assert parsed_schedule_name == original_schedule_name


@pytest.mark.unit
@pytest.mark.asyncio
class TestScheduleService:
    """Test suite for ScheduleService"""

    async def test_create_schedule_with_cron(
        self,
        schedule_service,
        mock_temporal_adapter,
        sample_agent,
        sample_create_schedule_request,
    ):
        """Test creating a schedule with cron expression"""
        # Given
        expected_schedule_id = build_schedule_id(
            sample_agent.id, sample_create_schedule_request.name
        )
        mock_description = create_mock_schedule_description(
            schedule_id=expected_schedule_id,
            workflow_name=sample_create_schedule_request.workflow_name,
            task_queue=sample_create_schedule_request.task_queue,
            cron_expressions=[sample_create_schedule_request.cron_expression],
        )
        mock_temporal_adapter.describe_schedule.return_value = mock_description

        # When
        result = await schedule_service.create_schedule(
            sample_agent, sample_create_schedule_request
        )

        # Then
        assert result is not None
        assert isinstance(result, ScheduleResponse)
        assert result.schedule_id == expected_schedule_id
        assert result.agent_id == sample_agent.id
        assert result.name == sample_create_schedule_request.name
        assert (
            result.action.workflow_name == sample_create_schedule_request.workflow_name
        )
        assert result.action.task_queue == sample_create_schedule_request.task_queue

        # Verify temporal adapter was called
        mock_temporal_adapter.create_schedule.assert_called_once()
        call_kwargs = mock_temporal_adapter.create_schedule.call_args[1]
        assert call_kwargs["schedule_id"] == expected_schedule_id
        assert call_kwargs["workflow"] == sample_create_schedule_request.workflow_name
        assert call_kwargs["task_queue"] == sample_create_schedule_request.task_queue
        assert call_kwargs["cron_expressions"] == [
            sample_create_schedule_request.cron_expression
        ]

    async def test_create_schedule_with_interval(
        self,
        schedule_service,
        mock_temporal_adapter,
        sample_agent,
        sample_create_schedule_request_interval,
    ):
        """Test creating a schedule with interval"""
        # Given
        expected_schedule_id = build_schedule_id(
            sample_agent.id, sample_create_schedule_request_interval.name
        )
        mock_description = create_mock_schedule_description(
            schedule_id=expected_schedule_id,
            workflow_name=sample_create_schedule_request_interval.workflow_name,
            task_queue=sample_create_schedule_request_interval.task_queue,
            intervals=[ScheduleIntervalSpec(every=timedelta(seconds=3600))],
        )
        mock_temporal_adapter.describe_schedule.return_value = mock_description

        # When
        result = await schedule_service.create_schedule(
            sample_agent, sample_create_schedule_request_interval
        )

        # Then
        assert result is not None
        assert isinstance(result, ScheduleResponse)
        assert result.schedule_id == expected_schedule_id

        # Verify temporal adapter was called with interval
        mock_temporal_adapter.create_schedule.assert_called_once()
        call_kwargs = mock_temporal_adapter.create_schedule.call_args[1]
        assert (
            call_kwargs["interval_seconds"]
            == sample_create_schedule_request_interval.interval_seconds
        )

    async def test_create_schedule_with_execution_timeout(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test creating a schedule with execution timeout"""
        # Given
        request = CreateScheduleRequest(
            name="timeout-task",
            workflow_name="test-workflow",
            task_queue="test-queue",
            cron_expression="0 0 * * *",
            execution_timeout_seconds=3600,
        )
        expected_schedule_id = build_schedule_id(sample_agent.id, request.name)
        mock_description = create_mock_schedule_description(
            schedule_id=expected_schedule_id,
            workflow_name=request.workflow_name,
            task_queue=request.task_queue,
        )
        mock_temporal_adapter.describe_schedule.return_value = mock_description

        # When
        result = await schedule_service.create_schedule(sample_agent, request)

        # Then
        assert result is not None
        mock_temporal_adapter.create_schedule.assert_called_once()
        call_kwargs = mock_temporal_adapter.create_schedule.call_args[1]
        assert call_kwargs["execution_timeout"] == timedelta(seconds=3600)

    async def test_create_schedule_paused(
        self, schedule_service, mock_temporal_adapter, sample_agent
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
        expected_schedule_id = build_schedule_id(sample_agent.id, request.name)
        mock_description = create_mock_schedule_description(
            schedule_id=expected_schedule_id,
            workflow_name=request.workflow_name,
            task_queue=request.task_queue,
            paused=True,
        )
        mock_temporal_adapter.describe_schedule.return_value = mock_description

        # When
        result = await schedule_service.create_schedule(sample_agent, request)

        # Then
        assert result is not None
        assert result.state == ScheduleState.PAUSED
        mock_temporal_adapter.create_schedule.assert_called_once()
        call_kwargs = mock_temporal_adapter.create_schedule.call_args[1]
        assert call_kwargs["paused"] is True

    async def test_get_schedule(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test getting a schedule by name"""
        # Given
        schedule_name = "test-schedule"
        schedule_id = build_schedule_id(sample_agent.id, schedule_name)
        mock_description = create_mock_schedule_description(
            schedule_id=schedule_id,
            workflow_name="test-workflow",
            task_queue="test-queue",
        )
        mock_temporal_adapter.describe_schedule.return_value = mock_description

        # When
        result = await schedule_service.get_schedule(sample_agent.id, schedule_name)

        # Then
        assert result is not None
        assert isinstance(result, ScheduleResponse)
        assert result.schedule_id == schedule_id
        assert result.name == schedule_name
        assert result.agent_id == sample_agent.id
        mock_temporal_adapter.describe_schedule.assert_called_once_with(schedule_id)

    async def test_get_schedule_paused(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test getting a paused schedule"""
        # Given
        schedule_name = "paused-schedule"
        schedule_id = build_schedule_id(sample_agent.id, schedule_name)
        mock_description = create_mock_schedule_description(
            schedule_id=schedule_id,
            workflow_name="test-workflow",
            task_queue="test-queue",
            paused=True,
        )
        mock_temporal_adapter.describe_schedule.return_value = mock_description

        # When
        result = await schedule_service.get_schedule(sample_agent.id, schedule_name)

        # Then
        assert result.state == ScheduleState.PAUSED

    async def test_list_schedules_for_agent(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test listing schedules for a specific agent"""
        # Given
        schedule_id_1 = build_schedule_id(sample_agent.id, "schedule-1")
        schedule_id_2 = build_schedule_id(sample_agent.id, "schedule-2")
        schedule_id_other = build_schedule_id("other-agent", "schedule-3")

        mock_schedule_1 = MagicMock()
        mock_schedule_1.id = schedule_id_1
        mock_schedule_1.info = MagicMock()
        mock_schedule_1.info.action = MagicMock(spec=ScheduleActionStartWorkflow)
        mock_schedule_1.info.action.workflow = "workflow-1"
        mock_schedule_1.info.next_action_times = [datetime.now(UTC)]
        mock_schedule_1.info.paused = False

        mock_schedule_2 = MagicMock()
        mock_schedule_2.id = schedule_id_2
        mock_schedule_2.info = MagicMock()
        mock_schedule_2.info.action = MagicMock(spec=ScheduleActionStartWorkflow)
        mock_schedule_2.info.action.workflow = "workflow-2"
        mock_schedule_2.info.next_action_times = []
        mock_schedule_2.info.paused = True

        mock_schedule_other = MagicMock()
        mock_schedule_other.id = schedule_id_other
        mock_schedule_other.info = MagicMock()
        mock_schedule_other.info.action = MagicMock(spec=ScheduleActionStartWorkflow)
        mock_schedule_other.info.action.workflow = "workflow-3"
        mock_schedule_other.info.next_action_times = []
        mock_schedule_other.info.paused = False

        mock_temporal_adapter.list_schedules.return_value = [
            mock_schedule_1,
            mock_schedule_2,
            mock_schedule_other,
        ]

        # When
        result = await schedule_service.list_schedules(agent_id=sample_agent.id)

        # Then
        assert result is not None
        assert isinstance(result, ScheduleListResponse)
        assert result.total == 2  # Only schedules for this agent
        assert len(result.schedules) == 2

        schedule_names = [s.name for s in result.schedules]
        assert "schedule-1" in schedule_names
        assert "schedule-2" in schedule_names

    async def test_list_schedules_all(self, schedule_service, mock_temporal_adapter):
        """Test listing all schedules without agent filter"""
        # Given
        mock_schedule = MagicMock()
        mock_schedule.id = "agent-1--schedule-1"
        mock_schedule.info = MagicMock()
        mock_schedule.info.action = MagicMock(spec=ScheduleActionStartWorkflow)
        mock_schedule.info.action.workflow = "workflow-1"
        mock_schedule.info.next_action_times = []
        mock_schedule.info.paused = False

        mock_temporal_adapter.list_schedules.return_value = [mock_schedule]

        # When
        result = await schedule_service.list_schedules(agent_id=None)

        # Then
        assert result is not None
        assert result.total == 1

    async def test_pause_schedule(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test pausing a schedule"""
        # Given
        schedule_name = "active-schedule"
        schedule_id = build_schedule_id(sample_agent.id, schedule_name)
        mock_description = create_mock_schedule_description(
            schedule_id=schedule_id,
            paused=True,
        )
        mock_temporal_adapter.describe_schedule.return_value = mock_description

        # When
        result = await schedule_service.pause_schedule(
            sample_agent.id, schedule_name, note="Maintenance"
        )

        # Then
        assert result is not None
        assert result.state == ScheduleState.PAUSED
        mock_temporal_adapter.pause_schedule.assert_called_once_with(
            schedule_id, note="Maintenance"
        )

    async def test_pause_schedule_without_note(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test pausing a schedule without a note"""
        # Given
        schedule_name = "active-schedule"
        schedule_id = build_schedule_id(sample_agent.id, schedule_name)
        mock_description = create_mock_schedule_description(
            schedule_id=schedule_id,
            paused=True,
        )
        mock_temporal_adapter.describe_schedule.return_value = mock_description

        # When
        result = await schedule_service.pause_schedule(sample_agent.id, schedule_name)

        # Then
        assert result is not None
        mock_temporal_adapter.pause_schedule.assert_called_once_with(
            schedule_id, note=None
        )

    async def test_unpause_schedule(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test unpausing a schedule"""
        # Given
        schedule_name = "paused-schedule"
        schedule_id = build_schedule_id(sample_agent.id, schedule_name)
        mock_description = create_mock_schedule_description(
            schedule_id=schedule_id,
            paused=False,
        )
        mock_temporal_adapter.describe_schedule.return_value = mock_description

        # When
        result = await schedule_service.unpause_schedule(
            sample_agent.id, schedule_name, note="Resuming operations"
        )

        # Then
        assert result is not None
        assert result.state == ScheduleState.ACTIVE
        mock_temporal_adapter.unpause_schedule.assert_called_once_with(
            schedule_id, note="Resuming operations"
        )

    async def test_unpause_schedule_without_note(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test unpausing a schedule without a note"""
        # Given
        schedule_name = "paused-schedule"
        schedule_id = build_schedule_id(sample_agent.id, schedule_name)
        mock_description = create_mock_schedule_description(
            schedule_id=schedule_id,
            paused=False,
        )
        mock_temporal_adapter.describe_schedule.return_value = mock_description

        # When
        result = await schedule_service.unpause_schedule(sample_agent.id, schedule_name)

        # Then
        assert result is not None
        mock_temporal_adapter.unpause_schedule.assert_called_once_with(
            schedule_id, note=None
        )

    async def test_trigger_schedule(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test triggering a schedule immediately"""
        # Given
        schedule_name = "scheduled-task"
        schedule_id = build_schedule_id(sample_agent.id, schedule_name)
        mock_description = create_mock_schedule_description(
            schedule_id=schedule_id,
        )
        mock_temporal_adapter.describe_schedule.return_value = mock_description

        # When
        result = await schedule_service.trigger_schedule(sample_agent.id, schedule_name)

        # Then
        assert result is not None
        mock_temporal_adapter.trigger_schedule.assert_called_once_with(schedule_id)

    async def test_delete_schedule(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test deleting a schedule"""
        # Given
        schedule_name = "schedule-to-delete"
        schedule_id = build_schedule_id(sample_agent.id, schedule_name)

        # When
        await schedule_service.delete_schedule(sample_agent.id, schedule_name)

        # Then
        mock_temporal_adapter.delete_schedule.assert_called_once_with(schedule_id)

    async def test_description_to_response_with_workflow_params(
        self, schedule_service, sample_agent
    ):
        """Test converting schedule description with workflow params"""
        # Given
        schedule_name = "task-with-params"
        schedule_id = build_schedule_id(sample_agent.id, schedule_name)

        # Create mock with args
        mock_action = MagicMock(spec=ScheduleActionStartWorkflow)
        mock_action.workflow = "test-workflow"
        mock_action.id = f"{schedule_id}-run"
        mock_action.task_queue = "test-queue"

        # Mock args with data attribute (simulating Temporal payload)
        mock_arg = MagicMock()
        mock_arg.data = b'{"key": "value"}'
        mock_action.args = [mock_arg]

        mock_spec = MagicMock(spec=ScheduleSpec)
        mock_spec.cron_expressions = ["0 0 * * *"]
        mock_spec.intervals = []
        mock_spec.start_at = None
        mock_spec.end_at = None

        mock_state = MagicMock(spec=TemporalScheduleState)
        mock_state.paused = False

        mock_schedule = MagicMock(spec=Schedule)
        mock_schedule.action = mock_action
        mock_schedule.spec = mock_spec
        mock_schedule.state = mock_state

        mock_info = MagicMock(spec=ScheduleInfo)
        mock_info.num_actions = 10
        mock_info.num_actions_missed_catchup_window = 1
        mock_info.next_action_times = []
        mock_info.recent_actions = []
        mock_info.create_time = datetime.now(UTC)

        mock_description = MagicMock(spec=ScheduleDescription)
        mock_description.schedule = mock_schedule
        mock_description.info = mock_info

        # When
        result = schedule_service._description_to_response(
            schedule_id, mock_description
        )

        # Then
        assert result.schedule_id == schedule_id
        assert result.name == schedule_name
        assert result.agent_id == sample_agent.id
        assert result.action.workflow_name == "test-workflow"
        assert result.num_actions_taken == 10
        assert result.num_actions_missed == 1
        assert result.action.workflow_params == [{"key": "value"}]

    async def test_description_to_response_with_intervals(
        self, schedule_service, sample_agent
    ):
        """Test converting schedule description with interval spec"""
        # Given
        schedule_name = "interval-task"
        schedule_id = build_schedule_id(sample_agent.id, schedule_name)

        mock_description = create_mock_schedule_description(
            schedule_id=schedule_id,
            intervals=[
                ScheduleIntervalSpec(every=timedelta(seconds=3600)),
                ScheduleIntervalSpec(every=timedelta(seconds=7200)),
            ],
        )

        # When
        result = schedule_service._description_to_response(
            schedule_id, mock_description
        )

        # Then
        assert result.spec.intervals_seconds == [3600, 7200]

    async def test_create_schedule_with_start_and_end_dates(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test creating a schedule with start and end dates"""
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
        expected_schedule_id = build_schedule_id(sample_agent.id, request.name)
        mock_description = create_mock_schedule_description(
            schedule_id=expected_schedule_id,
        )
        mock_temporal_adapter.describe_schedule.return_value = mock_description

        # When
        result = await schedule_service.create_schedule(sample_agent, request)

        # Then
        assert result is not None
        mock_temporal_adapter.create_schedule.assert_called_once()
        call_kwargs = mock_temporal_adapter.create_schedule.call_args[1]
        assert call_kwargs["start_at"] == start_at
        assert call_kwargs["end_at"] == end_at

    async def test_create_schedule_already_exists_error(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test that schedule already exists error propagates"""
        # Given
        request = CreateScheduleRequest(
            name="existing-task",
            workflow_name="test-workflow",
            task_queue="test-queue",
            cron_expression="0 0 * * *",
        )
        mock_temporal_adapter.create_schedule.side_effect = (
            TemporalScheduleAlreadyExistsError(
                message="Schedule already exists",
                detail="Schedule 'existing-task' already exists",
            )
        )

        # When/Then
        with pytest.raises(TemporalScheduleAlreadyExistsError):
            await schedule_service.create_schedule(sample_agent, request)

    async def test_get_schedule_not_found_error(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test that schedule not found error propagates"""
        # Given
        mock_temporal_adapter.describe_schedule.side_effect = (
            TemporalScheduleNotFoundError(
                message="Schedule not found",
                detail="Schedule 'nonexistent' not found",
            )
        )

        # When/Then
        with pytest.raises(TemporalScheduleNotFoundError):
            await schedule_service.get_schedule(sample_agent.id, "nonexistent")

    async def test_pause_schedule_not_found_error(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test that pause schedule not found error propagates"""
        # Given
        mock_temporal_adapter.pause_schedule.side_effect = (
            TemporalScheduleNotFoundError(
                message="Schedule not found",
                detail="Schedule 'nonexistent' not found",
            )
        )

        # When/Then
        with pytest.raises(TemporalScheduleNotFoundError):
            await schedule_service.pause_schedule(sample_agent.id, "nonexistent")

    async def test_delete_schedule_not_found_error(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test that delete schedule not found error propagates"""
        # Given
        mock_temporal_adapter.delete_schedule.side_effect = (
            TemporalScheduleNotFoundError(
                message="Schedule not found",
                detail="Schedule 'nonexistent' not found",
            )
        )

        # When/Then
        with pytest.raises(TemporalScheduleNotFoundError):
            await schedule_service.delete_schedule(sample_agent.id, "nonexistent")

    async def test_trigger_schedule_not_found_error(
        self, schedule_service, mock_temporal_adapter, sample_agent
    ):
        """Test that trigger schedule not found error propagates"""
        # Given
        mock_temporal_adapter.trigger_schedule.side_effect = (
            TemporalScheduleNotFoundError(
                message="Schedule not found",
                detail="Schedule 'nonexistent' not found",
            )
        )

        # When/Then
        with pytest.raises(TemporalScheduleNotFoundError):
            await schedule_service.trigger_schedule(sample_agent.id, "nonexistent")

    async def test_list_schedules_error(self, schedule_service, mock_temporal_adapter):
        """Test that list schedules error propagates"""
        # Given
        mock_temporal_adapter.list_schedules.side_effect = TemporalScheduleError(
            message="Failed to list schedules",
            detail="Temporal connection error",
        )

        # When/Then
        with pytest.raises(TemporalScheduleError):
            await schedule_service.list_schedules()
