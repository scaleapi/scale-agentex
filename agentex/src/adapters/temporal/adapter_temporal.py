from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import Depends
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleCalendarSpec,
    ScheduleDescription,
    ScheduleHandle,
    ScheduleIntervalSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleRange,
    ScheduleSpec,
    ScheduleState,
    ScheduleUpdate,
    ScheduleUpdateInput,
    WorkflowExecution,
    WorkflowHandle,
)
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from src.adapters.temporal.exceptions import (
    TemporalCancelError,
    TemporalConnectionError,
    TemporalError,
    TemporalInvalidArgumentError,
    TemporalQueryError,
    TemporalScheduleAlreadyExistsError,
    TemporalScheduleError,
    TemporalScheduleNotFoundError,
    TemporalSignalError,
    TemporalTerminateError,
    TemporalWorkflowAlreadyExistsError,
    TemporalWorkflowError,
    TemporalWorkflowNotFoundError,
)
from src.adapters.temporal.port import TemporalGateway
from src.utils.logging import make_logger
from src.utils.schedule_metrics import record_schedule_temporal_op

logger = make_logger(__name__)


class TemporalAdapter(TemporalGateway):
    """
    Implementation of the TemporalGateway interface using the Temporal Python SDK.
    Provides a clean abstraction over Temporal client operations with proper error handling.
    """

    def __init__(self, temporal_client: Client | None = None):
        """
        Initialize the Temporal adapter with a client instance.

        Args:
            temporal_client: The Temporal client (may be None if not configured)
        """
        self.client = temporal_client

    async def start_workflow(
        self,
        workflow: str | type,
        workflow_id: str,
        args: list[Any] | None = None,
        task_queue: str | None = None,
        execution_timeout: timedelta | None = None,
        retry_policy: RetryPolicy | None = None,
        id_reuse_policy: WorkflowIDReusePolicy | None = None,
        start_delay: timedelta | None = None,
    ) -> WorkflowHandle:
        """
        Start a new workflow execution.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            # Build workflow options
            options: dict[str, Any] = {
                "id": workflow_id,
            }

            if task_queue:
                options["task_queue"] = task_queue
            if execution_timeout:
                options["execution_timeout"] = execution_timeout
            if retry_policy:
                options["retry_policy"] = retry_policy
            if id_reuse_policy:
                options["id_reuse_policy"] = id_reuse_policy
            if start_delay:
                options["start_delay"] = start_delay

            # Start the workflow. Temporal's client.start_workflow takes a single
            # positional ``arg``; multiple workflow arguments must be passed via
            # the ``args`` keyword (spreading them positionally raises "takes from
            # 2 to 3 positional arguments").
            handle = await self.client.start_workflow(
                workflow,
                args=args if args else [],
                **options,
            )

            logger.info(f"Started workflow {workflow_id} successfully")
            return handle

        except WorkflowAlreadyStartedError as e:
            logger.error(f"Workflow {workflow_id} already exists: {e}")
            raise TemporalWorkflowAlreadyExistsError(
                message=f"Workflow with ID '{workflow_id}' already exists",
                detail=str(e),
            ) from e
        except ValueError as e:
            logger.error(f"Invalid arguments for workflow {workflow_id}: {e}")
            raise TemporalInvalidArgumentError(
                message=f"Invalid arguments provided for workflow '{workflow_id}'",
                detail=str(e),
            ) from e
        except Exception as e:
            logger.error(f"Failed to start workflow {workflow_id}: {e}")
            raise TemporalWorkflowError(
                message=f"Failed to start workflow '{workflow_id}'",
                detail=str(e),
            ) from e

    async def get_workflow_handle(
        self,
        workflow_id: str,
        run_id: str | None = None,
        first_execution_run_id: str | None = None,
    ) -> WorkflowHandle:
        """
        Get a handle to an existing workflow.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            handle = self.client.get_workflow_handle(
                workflow_id,
                run_id=run_id,
                first_execution_run_id=first_execution_run_id,
            )
            return handle
        except Exception as e:
            logger.error(f"Failed to get workflow handle for {workflow_id}: {e}")
            raise TemporalWorkflowNotFoundError(
                message=f"Workflow '{workflow_id}' not found",
                detail=str(e),
            ) from e

    async def signal_workflow(
        self,
        workflow_id: str,
        signal: str,
        arg: Any = None,
        run_id: str | None = None,
    ) -> None:
        """
        Send a signal to a running workflow.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            handle = self.client.get_workflow_handle(workflow_id, run_id=run_id)
            await handle.signal(signal, arg)
            logger.info(f"Sent signal '{signal}' to workflow {workflow_id}")
        except Exception as e:
            if "not found" in str(e).lower():
                logger.error(f"Workflow {workflow_id} not found: {e}")
                raise TemporalWorkflowNotFoundError(
                    message=f"Workflow '{workflow_id}' not found",
                    detail=str(e),
                ) from e
            logger.error(f"Failed to signal workflow {workflow_id}: {e}")
            raise TemporalSignalError(
                message=f"Failed to send signal '{signal}' to workflow '{workflow_id}'",
                detail=str(e),
            ) from e

    async def query_workflow(
        self,
        workflow_id: str,
        query: str,
        arg: Any = None,
        run_id: str | None = None,
    ) -> Any:
        """
        Query a workflow for its current state.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            handle = self.client.get_workflow_handle(workflow_id, run_id=run_id)
            if arg is not None:
                result = await handle.query(query, arg)
            else:
                result = await handle.query(query)
            logger.info(f"Queried workflow {workflow_id} with query '{query}'")
            return result
        except Exception as e:
            if "not found" in str(e).lower():
                logger.error(f"Workflow {workflow_id} not found: {e}")
                raise TemporalWorkflowNotFoundError(
                    message=f"Workflow '{workflow_id}' not found",
                    detail=str(e),
                ) from e
            logger.error(f"Failed to query workflow {workflow_id}: {e}")
            raise TemporalQueryError(
                message=f"Failed to execute query '{query}' on workflow '{workflow_id}'",
                detail=str(e),
            ) from e

    async def cancel_workflow(
        self,
        workflow_id: str,
        run_id: str | None = None,
    ) -> None:
        """
        Cancel a running workflow.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            handle = self.client.get_workflow_handle(workflow_id, run_id=run_id)
            await handle.cancel()
            logger.info(f"Cancelled workflow {workflow_id}")
        except Exception as e:
            if "not found" in str(e).lower():
                logger.error(f"Workflow {workflow_id} not found: {e}")
                raise TemporalWorkflowNotFoundError(
                    message=f"Workflow '{workflow_id}' not found",
                    detail=str(e),
                ) from e
            logger.error(f"Failed to cancel workflow {workflow_id}: {e}")
            raise TemporalCancelError(
                message=f"Failed to cancel workflow '{workflow_id}'",
                detail=str(e),
            ) from e

    async def terminate_workflow(
        self,
        workflow_id: str,
        reason: str | None = None,
        run_id: str | None = None,
    ) -> None:
        """
        Terminate a running workflow immediately.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            handle = self.client.get_workflow_handle(workflow_id, run_id=run_id)
            await handle.terminate(reason=reason)
            logger.info(f"Terminated workflow {workflow_id} with reason: {reason}")
        except Exception as e:
            if "not found" in str(e).lower():
                logger.error(f"Workflow {workflow_id} not found: {e}")
                raise TemporalWorkflowNotFoundError(
                    message=f"Workflow '{workflow_id}' not found",
                    detail=str(e),
                ) from e
            logger.error(f"Failed to terminate workflow {workflow_id}: {e}")
            raise TemporalTerminateError(
                message=f"Failed to terminate workflow '{workflow_id}'",
                detail=str(e),
            ) from e

    async def describe_workflow(
        self,
        workflow_id: str,
        run_id: str | None = None,
    ) -> WorkflowExecution:
        """
        Get detailed information about a workflow execution.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            handle = self.client.get_workflow_handle(workflow_id, run_id=run_id)
            description = await handle.describe()
            logger.info(f"Retrieved description for workflow {workflow_id}")
            return description
        except Exception as e:
            if "not found" in str(e).lower():
                logger.error(f"Workflow {workflow_id} not found: {e}")
                raise TemporalWorkflowNotFoundError(
                    message=f"Workflow '{workflow_id}' not found",
                    detail=str(e),
                ) from e
            logger.error(f"Failed to describe workflow {workflow_id}: {e}")
            raise TemporalWorkflowError(
                message=f"Failed to describe workflow '{workflow_id}'",
                detail=str(e),
            ) from e

    async def list_workflows(
        self,
        query: str | None = None,
        page_size: int = 100,
    ) -> list[WorkflowExecution]:
        """
        List workflow executions matching the query.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            workflows = []
            async for workflow in self.client.list_workflows(
                query=query,
                page_size=page_size,
            ):
                workflows.append(workflow)
                if len(workflows) >= page_size:
                    break

            logger.info(f"Listed {len(workflows)} workflows")
            return workflows
        except Exception as e:
            logger.error(f"Failed to list workflows: {e}")
            raise TemporalError(
                message="Failed to list workflows",
                detail=str(e),
            ) from e

    async def get_client(self) -> Client:
        """
        Get the underlying Temporal client instance.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")
        return self.client

    async def is_connected(self) -> bool:
        """
        Check if the Temporal client is connected and healthy.
        """
        if not self.client:
            return False

        try:
            # Try to list workflows with a very small limit to test connectivity
            async for _ in self.client.list_workflows(page_size=1):
                break
            return True
        except Exception as e:
            logger.warning(f"Temporal connectivity check failed: {e}")
            return False

    # ==================== Schedule Operations ====================

    async def create_schedule(
        self,
        schedule_id: str,
        workflow: str | type,
        workflow_id: str,
        args: list[Any] | None = None,
        task_queue: str | None = None,
        cron_expressions: list[str] | None = None,
        interval_seconds: int | None = None,
        execution_timeout: timedelta | None = None,
        start_at: Any | None = None,
        end_at: Any | None = None,
        paused: bool = False,
        time_zone_name: str | None = None,
        overlap_policy: str | None = None,
    ) -> ScheduleHandle:
        """
        Create a new schedule for recurring workflow execution.

        ``time_zone_name`` is an optional IANA timezone (e.g. ``America/New_York``)
        the cron expression is evaluated in; when omitted, cron is evaluated in
        UTC. Ignored for interval-based schedules.

        ``overlap_policy`` is an optional ScheduleOverlapPolicy name (e.g.
        ``"skip"``, ``"buffer_one"``) controlling what happens when a fire is due
        while a prior run is still executing. When omitted, Temporal's default
        (SKIP) applies.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        if not cron_expressions and not interval_seconds:
            raise TemporalInvalidArgumentError(
                message="Either cron_expressions or interval_seconds must be provided",
                detail="A schedule requires at least one scheduling specification",
            )

        try:
            # Build schedule spec
            spec_kwargs: dict[str, Any] = {}
            if time_zone_name:
                spec_kwargs["time_zone_name"] = time_zone_name
            spec = ScheduleSpec(
                cron_expressions=cron_expressions or [],
                intervals=[
                    ScheduleIntervalSpec(every=timedelta(seconds=interval_seconds))
                ]
                if interval_seconds
                else [],
                start_at=start_at,
                end_at=end_at,
                **spec_kwargs,
            )

            # Build workflow action
            action_kwargs: dict[str, Any] = {
                "id": workflow_id,
            }
            if task_queue:
                action_kwargs["task_queue"] = task_queue
            if execution_timeout:
                action_kwargs["execution_timeout"] = execution_timeout

            action = ScheduleActionStartWorkflow(
                workflow,
                *(args if args else []),
                **action_kwargs,
            )

            # Build schedule state
            state = ScheduleState(
                paused=paused,
            )

            # Build schedule policies (overlap), when requested
            schedule_kwargs: dict[str, Any] = {}
            if overlap_policy:
                schedule_kwargs["policy"] = SchedulePolicy(
                    overlap=ScheduleOverlapPolicy[overlap_policy.upper()]
                )

            # Create the schedule
            handle = await self.client.create_schedule(
                schedule_id,
                Schedule(
                    action=action,
                    spec=spec,
                    state=state,
                    **schedule_kwargs,
                ),
            )

            logger.info(f"Created schedule {schedule_id} successfully")
            record_schedule_temporal_op("create", "success")
            return handle

        except ScheduleAlreadyRunningError as e:
            logger.error(f"Schedule {schedule_id} already exists: {e}")
            record_schedule_temporal_op("create", "error")
            raise TemporalScheduleAlreadyExistsError(
                message=f"Schedule with ID '{schedule_id}' already exists",
                detail=str(e),
            ) from e
        except ValueError as e:
            logger.error(f"Invalid arguments for schedule {schedule_id}: {e}")
            record_schedule_temporal_op("create", "error")
            raise TemporalInvalidArgumentError(
                message=f"Invalid arguments provided for schedule '{schedule_id}'",
                detail=str(e),
            ) from e
        except Exception as e:
            logger.error(f"Failed to create schedule {schedule_id}: {e}")
            record_schedule_temporal_op("create", "error")
            raise TemporalScheduleError(
                message=f"Failed to create schedule '{schedule_id}'",
                detail=str(e),
            ) from e

    async def get_schedule(self, schedule_id: str) -> ScheduleHandle:
        """
        Get a handle to an existing schedule.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            handle = self.client.get_schedule_handle(schedule_id)
            # Verify the schedule exists by describing it
            await handle.describe()
            return handle
        except Exception as e:
            if "not found" in str(e).lower():
                logger.error(f"Schedule {schedule_id} not found: {e}")
                raise TemporalScheduleNotFoundError(
                    message=f"Schedule '{schedule_id}' not found",
                    detail=str(e),
                ) from e
            logger.error(f"Failed to get schedule {schedule_id}: {e}")
            raise TemporalScheduleError(
                message=f"Failed to get schedule '{schedule_id}'",
                detail=str(e),
            ) from e

    async def describe_schedule(self, schedule_id: str) -> ScheduleDescription:
        """
        Get detailed information about a schedule.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            handle = self.client.get_schedule_handle(schedule_id)
            description = await handle.describe()
            logger.info(f"Retrieved description for schedule {schedule_id}")
            return description
        except Exception as e:
            if "not found" in str(e).lower():
                logger.error(f"Schedule {schedule_id} not found: {e}")
                raise TemporalScheduleNotFoundError(
                    message=f"Schedule '{schedule_id}' not found",
                    detail=str(e),
                ) from e
            logger.error(f"Failed to describe schedule {schedule_id}: {e}")
            raise TemporalScheduleError(
                message=f"Failed to describe schedule '{schedule_id}'",
                detail=str(e),
            ) from e

    async def list_schedules(
        self,
        page_size: int = 100,
    ) -> list[Any]:
        """
        List all schedules.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            schedules = []
            # list_schedules() returns a coroutine that yields an async iterator
            async for schedule in await self.client.list_schedules(page_size=page_size):  # type: ignore[union-attr]
                schedules.append(schedule)
                if len(schedules) >= page_size:
                    break

            logger.info(f"Listed {len(schedules)} schedules")
            return schedules
        except Exception as e:
            logger.error(f"Failed to list schedules: {e}")
            raise TemporalError(
                message="Failed to list schedules",
                detail=str(e),
            ) from e

    async def pause_schedule(self, schedule_id: str, note: str | None = None) -> None:
        """
        Pause a schedule.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            handle = self.client.get_schedule_handle(schedule_id)
            await handle.pause(note=note or "Paused via API")
            logger.info(f"Paused schedule {schedule_id}")
        except Exception as e:
            if "not found" in str(e).lower():
                logger.error(f"Schedule {schedule_id} not found: {e}")
                raise TemporalScheduleNotFoundError(
                    message=f"Schedule '{schedule_id}' not found",
                    detail=str(e),
                ) from e
            logger.error(f"Failed to pause schedule {schedule_id}: {e}")
            raise TemporalScheduleError(
                message=f"Failed to pause schedule '{schedule_id}'",
                detail=str(e),
            ) from e

    async def unpause_schedule(self, schedule_id: str, note: str | None = None) -> None:
        """
        Unpause/resume a schedule.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            handle = self.client.get_schedule_handle(schedule_id)
            await handle.unpause(note=note or "Unpaused via API")
            logger.info(f"Unpaused schedule {schedule_id}")
        except Exception as e:
            if "not found" in str(e).lower():
                logger.error(f"Schedule {schedule_id} not found: {e}")
                raise TemporalScheduleNotFoundError(
                    message=f"Schedule '{schedule_id}' not found",
                    detail=str(e),
                ) from e
            logger.error(f"Failed to unpause schedule {schedule_id}: {e}")
            raise TemporalScheduleError(
                message=f"Failed to unpause schedule '{schedule_id}'",
                detail=str(e),
            ) from e

    async def trigger_schedule(self, schedule_id: str) -> None:
        """
        Trigger a schedule to run immediately.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            handle = self.client.get_schedule_handle(schedule_id)
            await handle.trigger()
            logger.info(f"Triggered schedule {schedule_id}")
        except Exception as e:
            if "not found" in str(e).lower():
                logger.error(f"Schedule {schedule_id} not found: {e}")
                raise TemporalScheduleNotFoundError(
                    message=f"Schedule '{schedule_id}' not found",
                    detail=str(e),
                ) from e
            logger.error(f"Failed to trigger schedule {schedule_id}: {e}")
            raise TemporalScheduleError(
                message=f"Failed to trigger schedule '{schedule_id}'",
                detail=str(e),
            ) from e

    async def skip_next_schedule_action(
        self, schedule_id: str, scheduled_time: datetime | None = None
    ) -> None:
        """
        Add a one-off exclusion for a scheduled action time.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            handle = self.client.get_schedule_handle(schedule_id)
            description = await handle.describe()
            action_time = scheduled_time or (
                description.info.next_action_times[0]
                if description.info.next_action_times
                else None
            )
            if action_time is None:
                return
            skip = self._one_off_skip_spec(
                action_time, description.schedule.spec.time_zone_name
            )

            def _apply(input: ScheduleUpdateInput) -> ScheduleUpdate:
                schedule = input.description.schedule
                schedule.spec.skip = [*(schedule.spec.skip or []), skip]
                return ScheduleUpdate(schedule=schedule)

            await handle.update(_apply)
            logger.info(f"Skipped next action for schedule {schedule_id}")
        except Exception as e:
            if "not found" in str(e).lower():
                logger.error(f"Schedule {schedule_id} not found: {e}")
                raise TemporalScheduleNotFoundError(
                    message=f"Schedule '{schedule_id}' not found",
                    detail=str(e),
                ) from e
            logger.error(f"Failed to skip next action for schedule {schedule_id}: {e}")
            raise TemporalScheduleError(
                message=f"Failed to skip next action for schedule '{schedule_id}'",
                detail=str(e),
            ) from e

    async def unskip_schedule_action(
        self, schedule_id: str, scheduled_time: datetime
    ) -> None:
        """
        Remove a one-off exclusion for a scheduled action time.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            handle = self.client.get_schedule_handle(schedule_id)
            description = await handle.describe()
            target = self._one_off_skip_spec(
                scheduled_time, description.schedule.spec.time_zone_name
            )

            def _apply(input: ScheduleUpdateInput) -> ScheduleUpdate:
                schedule = input.description.schedule
                schedule.spec.skip = [
                    skip
                    for skip in (schedule.spec.skip or [])
                    if not self._same_one_off_skip(skip, target)
                ]
                return ScheduleUpdate(schedule=schedule)

            await handle.update(_apply)
            logger.info(f"Unskipped action for schedule {schedule_id}")
        except Exception as e:
            if "not found" in str(e).lower():
                logger.error(f"Schedule {schedule_id} not found: {e}")
                raise TemporalScheduleNotFoundError(
                    message=f"Schedule '{schedule_id}' not found",
                    detail=str(e),
                ) from e
            logger.error(f"Failed to unskip action for schedule {schedule_id}: {e}")
            raise TemporalScheduleError(
                message=f"Failed to unskip action for schedule '{schedule_id}'",
                detail=str(e),
            ) from e

    @staticmethod
    def _one_off_skip_spec(
        scheduled_time: datetime, time_zone_name: str | None
    ) -> ScheduleCalendarSpec:
        if time_zone_name:
            scheduled_time = scheduled_time.astimezone(ZoneInfo(time_zone_name))

        def _range(value: int) -> list[ScheduleRange]:
            return [ScheduleRange(start=value, end=value)]

        return ScheduleCalendarSpec(
            second=_range(scheduled_time.second),
            minute=_range(scheduled_time.minute),
            hour=_range(scheduled_time.hour),
            day_of_month=_range(scheduled_time.day),
            month=_range(scheduled_time.month),
            year=_range(scheduled_time.year),
            # Specify all days of week so the exact date fields above decide
            # the match regardless of Temporal/Python weekday numbering.
            day_of_week=[ScheduleRange(start=0, end=6)],
            comment=f"Skipped via API at {datetime.now(UTC).isoformat()}",
        )

    @staticmethod
    def _same_one_off_skip(
        left: ScheduleCalendarSpec, right: ScheduleCalendarSpec
    ) -> bool:
        fields = ("second", "minute", "hour", "day_of_month", "month", "year")
        return all(
            len(getattr(left, field)) == 1
            and len(getattr(right, field)) == 1
            and getattr(left, field)[0].start == getattr(right, field)[0].start
            and getattr(left, field)[0].end == getattr(right, field)[0].end
            for field in fields
        )

    @staticmethod
    def extract_one_off_skip_times(description: ScheduleDescription) -> list[datetime]:
        time_zone_name = description.schedule.spec.time_zone_name
        timezone = ZoneInfo(time_zone_name) if time_zone_name else UTC
        skipped_times: list[datetime] = []

        for skip in description.schedule.spec.skip or []:
            values: dict[str, int] = {}
            for field, date_part in (
                ("second", "second"),
                ("minute", "minute"),
                ("hour", "hour"),
                ("day_of_month", "day"),
                ("month", "month"),
                ("year", "year"),
            ):
                ranges = getattr(skip, field)
                if len(ranges) != 1 or ranges[0].start != ranges[0].end:
                    values = {}
                    break
                values[date_part] = ranges[0].start

            if values:
                skipped_times.append(
                    datetime(
                        values["year"],
                        values["month"],
                        values["day"],
                        values["hour"],
                        values["minute"],
                        values["second"],
                        tzinfo=timezone,
                    ).astimezone(UTC)
                )

        return skipped_times

    async def update_schedule(
        self,
        schedule_id: str,
        cron_expressions: list[str] | None = None,
        interval_seconds: int | None = None,
        start_at: Any | None = None,
        end_at: Any | None = None,
        time_zone_name: str | None = None,
        paused: bool | None = None,
    ) -> None:
        """
        Update an existing schedule's spec and/or paused state.

        Rebuilds the schedule spec (cadence, window, timezone) from the provided
        values and replaces it, leaving the workflow action untouched. ``paused``
        is applied only when provided. The caller is expected to pass the full
        desired spec (cron XOR interval), mirroring ``create_schedule``.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        if not cron_expressions and not interval_seconds:
            raise TemporalInvalidArgumentError(
                message="Either cron_expressions or interval_seconds must be provided",
                detail="A schedule requires at least one scheduling specification",
            )

        spec_kwargs: dict[str, Any] = {}
        if time_zone_name:
            spec_kwargs["time_zone_name"] = time_zone_name
        new_spec = ScheduleSpec(
            cron_expressions=cron_expressions or [],
            intervals=[ScheduleIntervalSpec(every=timedelta(seconds=interval_seconds))]
            if interval_seconds
            else [],
            start_at=start_at,
            end_at=end_at,
            **spec_kwargs,
        )

        def _apply(input: ScheduleUpdateInput) -> ScheduleUpdate:
            schedule = input.description.schedule
            schedule.spec = new_spec
            if paused is not None:
                schedule.state.paused = paused
            return ScheduleUpdate(schedule=schedule)

        try:
            handle = self.client.get_schedule_handle(schedule_id)
            await handle.update(_apply)
            logger.info(f"Updated schedule {schedule_id}")
            record_schedule_temporal_op("update", "success")
        except Exception as e:
            if "not found" in str(e).lower():
                logger.error(f"Schedule {schedule_id} not found: {e}")
                record_schedule_temporal_op("update", "not_found")
                raise TemporalScheduleNotFoundError(
                    message=f"Schedule '{schedule_id}' not found",
                    detail=str(e),
                ) from e
            logger.error(f"Failed to update schedule {schedule_id}: {e}")
            record_schedule_temporal_op("update", "error")
            raise TemporalScheduleError(
                message=f"Failed to update schedule '{schedule_id}'",
                detail=str(e),
            ) from e

    async def delete_schedule(self, schedule_id: str) -> None:
        """
        Delete a schedule.
        """
        if not self.client:
            raise TemporalConnectionError("Temporal client is not connected")

        try:
            handle = self.client.get_schedule_handle(schedule_id)
            await handle.delete()
            logger.info(f"Deleted schedule {schedule_id}")
            record_schedule_temporal_op("delete", "success")
        except Exception as e:
            if "not found" in str(e).lower():
                logger.error(f"Schedule {schedule_id} not found: {e}")
                record_schedule_temporal_op("delete", "not_found")
                raise TemporalScheduleNotFoundError(
                    message=f"Schedule '{schedule_id}' not found",
                    detail=str(e),
                ) from e
            logger.error(f"Failed to delete schedule {schedule_id}: {e}")
            record_schedule_temporal_op("delete", "error")
            raise TemporalScheduleError(
                message=f"Failed to delete schedule '{schedule_id}'",
                detail=str(e),
            ) from e


# Dependency injection annotation for FastAPI
async def get_temporal_adapter() -> TemporalAdapter:
    """
    Factory function for dependency injection.
    Gets the temporal client from global dependencies.
    """
    from src.config.dependencies import GlobalDependencies

    global_deps = GlobalDependencies()
    await global_deps.load()
    client = global_deps.temporal_client
    return TemporalAdapter(temporal_client=client)


DTemporalAdapter = Annotated[TemporalAdapter, Depends(get_temporal_adapter)]
