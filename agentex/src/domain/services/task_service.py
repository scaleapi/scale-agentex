from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends

from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.adapters.streams.adapter_redis import DRedisStreamRepository
from src.api.schemas.authorization_types import AgentexResource
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.events import EventEntity
from src.domain.entities.task_message_updates import TaskMessageUpdateEntity
from src.domain.entities.task_messages import TaskMessageContentEntity
from src.domain.entities.task_stream_events import TaskStreamTaskUpdatedEventEntity
from src.domain.entities.tasks import TaskEntity, TaskRelationships, TaskStatus
from src.domain.repositories.event_repository import DEventRepository
from src.domain.repositories.task_repository import DTaskRepository
from src.domain.repositories.task_state_repository import DTaskStateRepository
from src.domain.services.agent_acp_service import DAgentACPService
from src.domain.services.authorization_service import DAuthorizationService
from src.utils.ids import orm_id
from src.utils.logging import make_logger
from src.utils.stream_topics import get_task_event_stream_topic

logger = make_logger(__name__)


class AgentTaskService:
    """
    Service for managing agent tasks and forwarding operations to ACP servers.
    """

    def __init__(
        self,
        acp_client: DAgentACPService,
        task_state_repository: DTaskStateRepository,
        task_repository: DTaskRepository,
        event_repository: DEventRepository,
        stream_repository: DRedisStreamRepository,
        authorization_service: DAuthorizationService,
    ):
        self.acp_client = acp_client
        self.task_state_repository = task_state_repository
        self.task_repository = task_repository
        self.event_repository = event_repository
        self.stream_repository = stream_repository
        self.authorization_service = authorization_service

    async def create_task(
        self,
        agent: AgentEntity,
        task_name: str | None = None,
        task_params: dict[str, Any] | None = None,
        task_metadata: dict[str, Any] | None = None,
    ) -> TaskEntity:
        """
        Create a new task record in the repository with single agent (maintains existing interface).

        Args:
            agent: The agent to create the task for
            task_name: The name of the task to be created
            task_params: The parameters for the task
            task_metadata: Caller-provided metadata to persist on the task row.
                Not forwarded to the agent.
        Returns:
            Task containing the created task info
        """
        # Register the task in the authorization graph before persisting: a
        # registration failure aborts the request with no orphaned row. If the
        # persist fails after a successful registration, the compensating
        # deregister_resource below prevents a dangling authorization entry.
        task_entity = TaskEntity(
            id=orm_id(),
            name=task_name,
            status=TaskStatus.RUNNING,
            status_reason="Task created, forwarding to ACP server",
            params=task_params,
            task_metadata=task_metadata,
        )
        await self.authorization_service.register_resource(
            AgentexResource.task(task_entity.id),
            parent=AgentexResource.agent(agent.id),
        )
        try:
            return await self.task_repository.create(
                agent_id=agent.id,
                task=task_entity,
            )
        except Exception:
            await self.authorization_service.deregister_resource(
                AgentexResource.task(task_entity.id),
            )
            raise

    async def create_task_and_forward_to_acp(
        self,
        agent: AgentEntity,
        task_name: str | None = None,
        task_params: dict[str, Any] | None = None,
    ) -> TaskEntity:
        """
        Create a new task record in the repository with single agent (maintains existing interface).
        Then, forward the task to the ACP server.

        Args:
            agent: The agent to create the task for
            task_params: The parameters for the task to be sent to the ACP server

        Returns:
            Task containing the created task info
        """
        task_entity = await self.create_task(
            agent=agent,
            task_name=task_name,
            task_params=task_params,
        )

        if agent.acp_type == ACPType.SYNC:
            logger.info(
                "For sync agents, there are no initialization handlers, skipping ACP call"
            )
            return task_entity
        try:
            await self.acp_client.create_task(
                agent=agent,
                task=task_entity,
                acp_url=agent.acp_url,
                params=task_params,
            )
            return task_entity
        except Exception as e:
            logger.error(f"Error creating task in ACP: {e}")
            await self.fail_task(task_entity, str(e))
            raise e from e

    async def forward_task_to_acp(
        self,
        agent: AgentEntity,
        task: TaskEntity,
        task_params: dict[str, Any] | None = None,
        acp_url: str | None = None,
    ) -> TaskEntity:
        try:
            await self.acp_client.create_task(
                agent=agent,
                task=task,
                acp_url=acp_url or agent.acp_url,
                params=task_params,
            )
        except Exception as e:
            logger.error(f"Error creating task in ACP: {e}")
            await self.fail_task(task, str(e))
            raise e from e

        # The forward succeeded: the agent has accepted the task. If this task
        # was left FAILED by an earlier forward attempt (e.g. the agent was
        # unavailable the first time task/create was called), clear that stale
        # failure now that the agent has accepted it. Otherwise the task — and
        # the task/create RPC response — would keep reporting the old error even
        # though the task is actually running.
        if task.status == TaskStatus.FAILED:
            task.status = TaskStatus.RUNNING
            task.status_reason = "Task forwarded to ACP server"
            task = await self.update_task(task)
        return task

    async def fail_task(self, task: TaskEntity, reason: str) -> None:
        task.status = TaskStatus.FAILED
        task.status_reason = reason
        await self.task_repository.update(task)

    async def get_task(
        self,
        id: str | None = None,
        name: str | None = None,
        relationships: list[TaskRelationships] | None = None,
    ) -> TaskEntity:
        """
        Get a task from the repository.
        """
        return await self.task_repository.get(
            id=id, name=name, relationships=relationships
        )

    async def transition_task_status(
        self,
        task_id: str,
        expected_status: TaskStatus,
        new_status: TaskStatus,
        status_reason: str,
        task_metadata: dict | None = None,
    ) -> TaskEntity | None:
        """
        Atomically transition task status. Returns None if the expected status didn't match.
        Publishes a task_updated event on success.
        """
        updated_task = await self.task_repository.transition_status(
            task_id=task_id,
            expected_status=expected_status,
            new_status=new_status,
            status_reason=status_reason,
            task_metadata=task_metadata,
        )
        if updated_task is None:
            return None

        try:
            topic = get_task_event_stream_topic(task_id=task_id)
            await self.stream_repository.send_data(
                topic,
                TaskStreamTaskUpdatedEventEntity(
                    type="task_updated", task=updated_task
                ).model_dump(mode="json"),
            )
            logger.info(f"task_updated event published to topic: {topic}")
        except Exception as e:
            logger.error(
                f"Error sending task_updated event to stream: {e}", exc_info=True
            )

        return updated_task

    async def update_task(self, task: TaskEntity) -> TaskEntity:
        """
        Update a task in the repository.
        """
        updated_task = await self.task_repository.update(task)

        try:
            # The Redis adapter now handles binary data properly
            topic = get_task_event_stream_topic(task_id=task.id)
            await self.stream_repository.send_data(
                topic,
                TaskStreamTaskUpdatedEventEntity(
                    type="task_updated", task=updated_task
                ).model_dump(mode="json"),
            )
            logger.info(f"task_updated event published to topic: {topic}")
        except Exception as e:
            logger.error(
                f"Error sending task_updated event to stream: {e}", exc_info=True
            )

        return updated_task

    async def merge_task_params(self, task_id: str, patch: dict) -> TaskEntity | None:
        """Atomically shallow-merge ``patch`` into ``tasks.params``. Returns
        the updated entity, or ``None`` if no task with ``task_id`` exists.

        Lets callers update agent config on the task row in place; the agent
        picks up the new values when it next reads ``task.params``.
        """
        return await self.task_repository.merge_params(task_id, patch)

    async def delete_task(self, id: str | None = None, name: str | None = None) -> None:
        """
        Delete a task from the repository.
        """
        # Delete first (Postgres is the source of truth for existence), then
        # deregister best-effort: a deregister failure is logged and swallowed
        # rather than failing a delete that already succeeded.
        # Resolve the id before the delete so we can pass it to deregister_resource;
        # looking it up by name afterwards would race. If the name doesn't resolve,
        # swallow ItemDoesNotExist and let delete() surface its own native error
        # so the missing-task error contract is unchanged.
        task_id_for_deregister: str | None = id
        if task_id_for_deregister is None and name is not None:
            try:
                task = await self.task_repository.get(name=name)
                task_id_for_deregister = task.id
            except ItemDoesNotExist:
                task_id_for_deregister = None

        await self.task_repository.delete(id=id, name=name)

        if task_id_for_deregister is not None:
            try:
                await self.authorization_service.deregister_resource(
                    AgentexResource.task(task_id_for_deregister),
                )
            except Exception:
                logger.exception(
                    "task authorization deregister failed for task %s after successful delete; "
                    "the deregistration failure has been swallowed",
                    task_id_for_deregister,
                )

    async def list_tasks(
        self,
        *,
        limit: int,
        page_number: int,
        id: str | list[str] | None = None,
        agent_id: str | None = None,
        agent_name: str | None = None,
        status: TaskStatus | list[TaskStatus] | None = None,
        task_metadata: dict | None = None,
        order_by: str | None = None,
        order_direction: str = "desc",
        relationships: list[TaskRelationships] | None = None,
    ) -> list[TaskEntity]:
        """
        List all tasks from the repository.
        """
        task_filters: dict = {}
        if id is not None:
            task_filters["id"] = id
        if status is not None:
            task_filters["status"] = status

        return await self.task_repository.list_with_join(
            task_filters=task_filters or None,
            agent_id=agent_id,
            agent_name=agent_name,
            task_metadata=task_metadata,
            order_by=order_by,
            order_direction=order_direction,
            limit=limit,
            page_number=page_number,
            relationships=relationships,
        )

    async def send_message(
        self,
        agent: AgentEntity,
        task: TaskEntity,
        content: TaskMessageContentEntity,
        acp_url: str,
    ) -> TaskMessageContentEntity:
        """Send a message to a running task"""
        return await self.acp_client.send_message(
            agent=agent,
            task=task,
            content=content,
            acp_url=acp_url,
        )

    async def send_message_stream(
        self,
        agent: AgentEntity,
        task: TaskEntity,
        content: TaskMessageContentEntity,
        acp_url: str,
    ) -> AsyncIterator[TaskMessageUpdateEntity]:
        """Send a message to a running task and stream the response"""
        logger.info(f"TaskService: Sending message stream for task {task.id}")
        async for chunk in self.acp_client.send_message_stream(
            agent=agent,
            task=task,
            content=content,
            acp_url=acp_url,
        ):
            yield chunk

    async def cancel_task(
        self, agent: AgentEntity, task: TaskEntity, acp_url: str
    ) -> TaskEntity:
        """Cancel a running (or interrupted) task."""
        await self.acp_client.cancel_task(agent=agent, task=task, acp_url=acp_url)

        # Compare-and-swap to CANCELED on the observed non-terminal source status
        # (mirrors interrupt_task). If the task moved to another status during the
        # ACP call (the agent completed/failed it, or it was concurrently modified),
        # leave that status intact rather than clobbering it with CANCELED.
        current = await self.task_repository.get(id=task.id)
        if current.status not in (TaskStatus.RUNNING, TaskStatus.INTERRUPTED):
            logger.info(
                f"Cancel for task {task.id} not applied: task is no longer running "
                f"(current status: {current.status}); leaving its status intact."
            )
            return current
        updated = await self.transition_task_status(
            task_id=task.id,
            expected_status=current.status,
            new_status=TaskStatus.CANCELED,
            status_reason="Task canceled by user",
        )
        return updated if updated is not None else await self.task_repository.get(id=task.id)

    async def interrupt_task(
        self, agent: AgentEntity, task: TaskEntity, acp_url: str
    ) -> TaskEntity:
        """Forward a task/interrupt to the agent (courier only; no status write).

        Interrupt is a COOPERATIVE action, unlike cancel. The control plane only
        forwards the request to the agent pod (same as event/send); the agent is
        responsible for stopping its in-flight turn and then recording INTERRUPTED
        via the REST POST /tasks/{id}/interrupt route (like the other task-state
        routes). The control plane never writes status here — so an agent that does
        not implement interrupt simply keeps running and its status stays honest.
        Resume back to RUNNING is owned by the control plane (see _get_or_create_task).
        """
        await self.acp_client.interrupt_task(agent=agent, task=task, acp_url=acp_url)
        return await self.task_repository.get(id=task.id)

    async def resume_interrupted_task(self, task_id: str) -> TaskEntity | None:
        """Atomically resume an INTERRUPTED task back to RUNNING on next-turn start.

        Non-terminal transition (INTERRUPTED -> RUNNING). Returns None if the task
        was not INTERRUPTED (e.g. it was concurrently canceled), so callers can
        keep the task as-is rather than clobbering a terminal status.
        """
        return await self.transition_task_status(
            task_id=task_id,
            expected_status=TaskStatus.INTERRUPTED,
            new_status=TaskStatus.RUNNING,
            status_reason="Task resumed on next turn",
        )

    async def create_event_and_forward_to_acp(
        self,
        agent: AgentEntity,
        task: TaskEntity,
        acp_url: str,
        content: TaskMessageContentEntity | None = None,
        request_headers: dict[str, str] | None = None,
    ) -> EventEntity:
        """Create an event and forward it to the ACP server"""
        event = await self.event_repository.create(
            id=orm_id(),
            task_id=task.id,
            agent_id=agent.id,
            content=content,
        )
        await self.acp_client.send_event(
            agent=agent,
            event=event,
            task=task,
            acp_url=acp_url,
            request_headers=request_headers,
        )
        return event


DAgentTaskService = Annotated[AgentTaskService, Depends(AgentTaskService)]
