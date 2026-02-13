from datetime import datetime, timedelta
from typing import Annotated, Any, cast

from fastapi import Depends
from temporalio.client import ScheduleActionStartWorkflow, ScheduleDescription

from src.adapters.temporal.adapter_temporal import DTemporalAdapter
from src.api.schemas.schedules import (
    CreateScheduleRequest,
    ScheduleActionInfo,
    ScheduleListItem,
    ScheduleListResponse,
    ScheduleResponse,
    ScheduleSpecInfo,
    ScheduleState,
)
from src.domain.entities.agents import AgentEntity
from src.utils.logging import make_logger

logger = make_logger(__name__)

# Schedule ID format: {agent_id}--{schedule_name}
SCHEDULE_ID_SEPARATOR = "--"


def build_schedule_id(agent_id: str, schedule_name: str) -> str:
    """Build a schedule ID from agent ID and schedule name."""
    return f"{agent_id}{SCHEDULE_ID_SEPARATOR}{schedule_name}"


def parse_schedule_id(schedule_id: str) -> tuple[str, str]:
    """Parse a schedule ID into (agent_id, schedule_name)."""
    parts = schedule_id.split(SCHEDULE_ID_SEPARATOR, 1)
    if len(parts) != 2:
        return schedule_id, ""
    return parts[0], parts[1]


class ScheduleService:
    """
    Service for managing Temporal schedules scoped to agents.
    """

    def __init__(
        self,
        temporal_adapter: DTemporalAdapter,
    ):
        self.temporal_adapter = temporal_adapter

    async def create_schedule(
        self,
        agent: AgentEntity,
        request: CreateScheduleRequest,
    ) -> ScheduleResponse:
        """
        Create a new schedule for recurring workflow execution.

        Args:
            agent: The agent this schedule belongs to
            request: The schedule creation request

        Returns:
            ScheduleResponse with the created schedule details
        """
        schedule_id = build_schedule_id(agent.id, request.name)
        workflow_id_prefix = f"{schedule_id}-run"

        # Build args for the workflow
        args = [request.workflow_params] if request.workflow_params else None

        # Convert cron_expression to list if provided
        cron_expressions = (
            [request.cron_expression] if request.cron_expression else None
        )

        # Convert execution timeout to timedelta
        execution_timeout = (
            timedelta(seconds=request.execution_timeout_seconds)
            if request.execution_timeout_seconds
            else None
        )

        await self.temporal_adapter.create_schedule(
            schedule_id=schedule_id,
            workflow=request.workflow_name,
            workflow_id=workflow_id_prefix,
            args=args,
            task_queue=request.task_queue,
            cron_expressions=cron_expressions,
            interval_seconds=request.interval_seconds,
            execution_timeout=execution_timeout,
            start_at=request.start_at,
            end_at=request.end_at,
            paused=request.paused,
        )

        # Fetch and return the created schedule
        return await self.get_schedule(agent.id, request.name)

    async def get_schedule(self, agent_id: str, schedule_name: str) -> ScheduleResponse:
        """
        Get details of a schedule.

        Args:
            agent_id: The agent ID
            schedule_name: The schedule name

        Returns:
            ScheduleResponse with schedule details
        """
        schedule_id = build_schedule_id(agent_id, schedule_name)
        description = await self.temporal_adapter.describe_schedule(schedule_id)

        return self._description_to_response(schedule_id, description)

    async def list_schedules(
        self, agent_id: str | None = None, page_size: int = 100
    ) -> ScheduleListResponse:
        """
        List schedules, optionally filtered by agent.

        Args:
            agent_id: Optional agent ID to filter schedules
            page_size: Number of results to return

        Returns:
            ScheduleListResponse with list of schedules
        """
        schedules = await self.temporal_adapter.list_schedules(page_size=page_size)

        items = []
        for schedule in schedules:
            # Parse agent_id from schedule_id
            parsed_agent_id, schedule_name = parse_schedule_id(schedule.id)

            # Filter by agent_id if provided
            if agent_id and parsed_agent_id != agent_id:
                continue

            # Extract workflow name from action if available
            workflow_name = None
            if hasattr(schedule, "info") and hasattr(schedule.info, "action"):
                action = schedule.info.action
                if isinstance(action, ScheduleActionStartWorkflow):
                    workflow_name = action.workflow

            # Extract next action time
            next_action_time = None
            if hasattr(schedule, "info") and schedule.info.next_action_times:
                next_action_time = schedule.info.next_action_times[0]

            # Determine state
            state = ScheduleState.ACTIVE
            if hasattr(schedule, "info") and hasattr(schedule.info, "paused"):
                state = (
                    ScheduleState.PAUSED
                    if schedule.info.paused
                    else ScheduleState.ACTIVE
                )

            items.append(
                ScheduleListItem(
                    schedule_id=schedule.id,
                    name=schedule_name or schedule.id,
                    agent_id=parsed_agent_id,
                    state=state,
                    workflow_name=workflow_name,
                    next_action_time=next_action_time,
                )
            )

        return ScheduleListResponse(
            schedules=items,
            total=len(items),
        )

    async def pause_schedule(
        self, agent_id: str, schedule_name: str, note: str | None = None
    ) -> ScheduleResponse:
        """
        Pause a schedule.

        Args:
            agent_id: The agent ID
            schedule_name: The schedule name
            note: Optional note explaining why the schedule was paused

        Returns:
            ScheduleResponse with updated schedule details
        """
        schedule_id = build_schedule_id(agent_id, schedule_name)
        await self.temporal_adapter.pause_schedule(schedule_id, note=note)
        return await self.get_schedule(agent_id, schedule_name)

    async def unpause_schedule(
        self, agent_id: str, schedule_name: str, note: str | None = None
    ) -> ScheduleResponse:
        """
        Unpause/resume a schedule.

        Args:
            agent_id: The agent ID
            schedule_name: The schedule name
            note: Optional note explaining why the schedule was unpaused

        Returns:
            ScheduleResponse with updated schedule details
        """
        schedule_id = build_schedule_id(agent_id, schedule_name)
        await self.temporal_adapter.unpause_schedule(schedule_id, note=note)
        return await self.get_schedule(agent_id, schedule_name)

    async def trigger_schedule(
        self, agent_id: str, schedule_name: str
    ) -> ScheduleResponse:
        """
        Trigger a schedule to run immediately.

        Args:
            agent_id: The agent ID
            schedule_name: The schedule name

        Returns:
            ScheduleResponse with updated schedule details
        """
        schedule_id = build_schedule_id(agent_id, schedule_name)
        await self.temporal_adapter.trigger_schedule(schedule_id)
        return await self.get_schedule(agent_id, schedule_name)

    async def delete_schedule(self, agent_id: str, schedule_name: str) -> None:
        """
        Delete a schedule.

        Args:
            agent_id: The agent ID
            schedule_name: The schedule name
        """
        schedule_id = build_schedule_id(agent_id, schedule_name)
        await self.temporal_adapter.delete_schedule(schedule_id)

    def _description_to_response(
        self, schedule_id: str, description: ScheduleDescription
    ) -> ScheduleResponse:
        """
        Convert a Temporal ScheduleDescription to a ScheduleResponse.

        Args:
            schedule_id: The schedule ID
            description: Temporal ScheduleDescription object

        Returns:
            ScheduleResponse
        """
        # Parse agent_id and name from schedule_id
        agent_id, schedule_name = parse_schedule_id(schedule_id)

        # Extract action info
        action = description.schedule.action
        workflow_name = ""
        workflow_id_prefix = ""
        task_queue = ""
        workflow_params: list[Any] | None = None

        if isinstance(action, ScheduleActionStartWorkflow):
            workflow_name = action.workflow
            workflow_id_prefix = action.id
            task_queue = action.task_queue or ""
            # Convert Temporal Payload objects to JSON-serializable format
            # The args are raw Temporal payloads that can't be directly serialized
            if action.args:
                try:
                    # Try to extract data from payloads if they have a data attribute
                    workflow_params = []
                    for arg in action.args:
                        if hasattr(arg, "data"):
                            # Decode bytes to string if possible
                            try:
                                import json

                                workflow_params.append(
                                    json.loads(arg.data.decode("utf-8"))
                                )
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                workflow_params.append(str(arg.data))
                        else:
                            workflow_params.append(str(arg))
                except Exception:
                    # If conversion fails, just indicate params exist but can't be displayed
                    workflow_params = None
            else:
                workflow_params = None

        # Extract spec info
        spec = description.schedule.spec
        cron_expressions = list(spec.cron_expressions) if spec.cron_expressions else []
        intervals_seconds = [
            int(interval.every.total_seconds()) for interval in (spec.intervals or [])
        ]

        # Extract state
        state = ScheduleState.ACTIVE
        if description.schedule.state and description.schedule.state.paused:
            state = ScheduleState.PAUSED

        # Extract info
        info = description.info
        num_actions_taken = info.num_actions if hasattr(info, "num_actions") else 0
        num_actions_missed = (
            info.num_actions_missed_catchup_window
            if hasattr(info, "num_actions_missed_catchup_window")
            else 0
        )
        next_action_times = (
            list(info.next_action_times) if info.next_action_times else []
        )
        last_action_time = None
        if hasattr(info, "recent_actions") and info.recent_actions:
            # ScheduleActionResult has started_at (when action started) and scheduled_at (when it was scheduled)
            last_action = info.recent_actions[-1]
            last_action_time = getattr(last_action, "started_at", None) or getattr(
                last_action, "scheduled_at", None
            )
        created_at: datetime | None = (
            cast(datetime, info.create_time)
            if hasattr(info, "create_time") and info.create_time
            else None
        )

        return ScheduleResponse(
            schedule_id=schedule_id,
            name=schedule_name or schedule_id,
            agent_id=agent_id,
            state=state,
            action=ScheduleActionInfo(
                workflow_name=workflow_name,
                workflow_id_prefix=workflow_id_prefix,
                task_queue=task_queue,
                workflow_params=workflow_params,
            ),
            spec=ScheduleSpecInfo(
                cron_expressions=cron_expressions,
                intervals_seconds=intervals_seconds,
                start_at=spec.start_at,
                end_at=spec.end_at,
            ),
            num_actions_taken=num_actions_taken,
            num_actions_missed=num_actions_missed,
            next_action_times=next_action_times,
            last_action_time=last_action_time,
            created_at=created_at,
        )


DScheduleService = Annotated[ScheduleService, Depends(ScheduleService)]
