from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends

from src.adapters.streams.adapter_redis import DRedisStreamRepository
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.events import EventEntity
from src.domain.entities.task_message_updates import TaskMessageUpdateEntity
from src.domain.entities.task_messages import TaskMessageContentEntity
from src.domain.entities.task_stream_events import TaskStreamTaskUpdatedEventEntity
from src.domain.entities.tasks import TaskEntity, TaskRelationships, TaskStatus
from src.domain.repositories.event_repository import DEventRepository
from src.domain.repositories.task_repository import DTaskRepository
from src.domain.services.agent_acp_service import DAgentACPService
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
        task_repository: DTaskRepository,
        event_repository: DEventRepository,
        stream_repository: DRedisStreamRepository,
    ):
        self.acp_client = acp_client
        self.task_repository = task_repository
        self.event_repository = event_repository
        self.stream_repository = stream_repository

    async def create_task(
        self,
        agent: AgentEntity,
        task_name: str | None = None,
        task_params: dict[str, Any] | None = None,
    ) -> TaskEntity:
        """
        Create a new task record in the repository with single agent (maintains existing interface).

        Args:
            agent: The agent to create the task for
            task_name: The name of the task to be created
            task_params: The parameters for the task
        Returns:
            Task containing the created task info
        """

        task_entity = await self.task_repository.create(
            agent_id=agent.id,
            task=TaskEntity(
                id=orm_id(),
                name=task_name,
                status=TaskStatus.RUNNING,
                status_reason="Task created, forwarding to ACP server",
                params=task_params,
            ),
        )
        return task_entity

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
            agent=agent, task_name=task_name, task_params=task_params
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
    ) -> None:
        try:
            await self.acp_client.create_task(
                agent=agent,
                task=task,
                acp_url=agent.acp_url,
                params=task_params,
            )
        except Exception as e:
            logger.error(f"Error creating task in ACP: {e}")
            await self.fail_task(task, str(e))
            raise e from e

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

    async def delete_task(self, id: str | None = None, name: str | None = None) -> None:
        """
        Delete a task from the repository.
        """
        await self.task_repository.delete(id=id, name=name)

    async def list_tasks(
        self,
        *,
        limit: int,
        page_number: int,
        id: str | list[str] | None = None,
        agent_id: str | None = None,
        agent_name: str | None = None,
        order_by: str | None = None,
        order_direction: str = "desc",
        relationships: list[TaskRelationships] | None = None,
    ) -> list[TaskEntity]:
        """
        List all tasks from the repository.
        """

        return await self.task_repository.list_with_join(
            task_filters={"id": id} if id is not None else None,
            agent_id=agent_id,
            agent_name=agent_name,
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
        """Cancel a running task"""
        await self.acp_client.cancel_task(agent=agent, task=task, acp_url=acp_url)

        task = await self.task_repository.get(id=task.id)
        task.status = TaskStatus.CANCELED
        task.status_reason = "Task canceled by user"
        return await self.task_repository.update(task)

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
