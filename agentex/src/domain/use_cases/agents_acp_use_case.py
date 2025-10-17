import json
from collections.abc import AsyncIterator, Callable
from typing import Annotated, Any

from fastapi import Depends

from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.authorization_types import (
    AgentexResource,
)
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.agents_rpc import (
    ACP_TYPE_TO_ALLOWED_RPC_METHODS,
    AgentRPCMethod,
    AgentRPCRequestEntity,
    CancelTaskRequestEntity,
    CreateTaskRequestEntity,
    SendEventRequestEntity,
    SendMessageRequestEntity,
)
from src.domain.entities.events import EventEntity
from src.domain.entities.task_message_updates import (
    DeltaType,
    StreamTaskMessageDeltaEntity,
    StreamTaskMessageDoneEntity,
    StreamTaskMessageFullEntity,
    StreamTaskMessageStartEntity,
    TaskMessageDeltaEntity,
    TaskMessageUpdateEntity,
)
from src.domain.entities.task_messages import (
    DataContentEntity,
    MessageAuthor,
    ReasoningContentEntity,
    TaskMessageContentEntity,
    TaskMessageEntity,
    TextContentEntity,
    ToolRequestContentEntity,
    ToolResponseContentEntity,
)
from src.domain.entities.tasks import TaskEntity
from src.domain.exceptions import ClientError
from src.domain.mixins.task_messages.task_message_mixin import TaskMessageMixin
from src.domain.repositories.agent_repository import DAgentRepository
from src.domain.services.agent_acp_service import DAgentACPService
from src.domain.services.authorization_service import DAuthorizationService
from src.domain.services.task_message_service import DTaskMessageService
from src.domain.services.task_service import DAgentTaskService
from src.utils.logging import make_logger

logger = make_logger(__name__)


class DeltaAccumulator:
    def __init__(self):
        self._accumulated_deltas: list[TaskMessageDeltaEntity] = []
        self._delta_type: DeltaType | None = None

    def add_delta(self, delta: TaskMessageDeltaEntity):
        if self._delta_type is None:
            if delta.type == DeltaType.TEXT:
                self._delta_type = DeltaType.TEXT
            elif delta.type == DeltaType.DATA:
                self._delta_type = DeltaType.DATA
            elif delta.type == DeltaType.TOOL_REQUEST:
                self._delta_type = DeltaType.TOOL_REQUEST
            elif delta.type == DeltaType.TOOL_RESPONSE:
                self._delta_type = DeltaType.TOOL_RESPONSE
            elif delta.type == DeltaType.REASONING_CONTENT:
                self._delta_type = DeltaType.REASONING_CONTENT
            elif delta.type == DeltaType.REASONING_SUMMARY:
                self._delta_type = DeltaType.REASONING_SUMMARY
            else:
                raise ValueError(f"Unknown delta type: {delta.type}")
        else:
            if self._delta_type != delta.type:
                raise ClientError(
                    f"Delta type mismatch: {self._delta_type} != {delta.type}"
                )

        self._accumulated_deltas.append(delta)

    def convert_to_content(self) -> TaskMessageContentEntity:
        if self._delta_type == DeltaType.TEXT:
            text_content_str = "".join(
                [
                    delta.text_delta
                    for delta in self._accumulated_deltas
                    if delta.text_delta is not None
                ]
            )
            return TextContentEntity(
                author=MessageAuthor.AGENT,
                content=text_content_str,
            )
        elif self._delta_type == DeltaType.DATA:
            data_content_str = "".join(
                [
                    delta.data_delta
                    for delta in self._accumulated_deltas
                    if delta.data_delta is not None
                ]
            )
            try:
                data = json.loads(data_content_str)
            except json.JSONDecodeError as e:
                raise ClientError(
                    f"Accumulated data content is not valid JSON: {data_content_str}"
                ) from e
            return DataContentEntity(
                author=MessageAuthor.AGENT,
                data=data,
            )
        elif self._delta_type == DeltaType.TOOL_REQUEST:
            arguments_content_str = "".join(
                [
                    delta.arguments_delta
                    for delta in self._accumulated_deltas
                    if delta.arguments_delta is not None
                ]
            )
            try:
                arguments = json.loads(arguments_content_str)
            except json.JSONDecodeError as e:
                raise ClientError(
                    f"Accumulated tool request arguments is not valid JSON: {arguments_content_str}"
                ) from e
            return ToolRequestContentEntity(
                author=MessageAuthor.AGENT,
                tool_call_id=self._accumulated_deltas[0].tool_call_id,
                name=self._accumulated_deltas[0].name,
                arguments=arguments,
            )
        elif self._delta_type == DeltaType.TOOL_RESPONSE:
            tool_response_content_str = "".join(
                [
                    delta.content_delta
                    for delta in self._accumulated_deltas
                    if delta.content_delta is not None
                ]
            )
            return ToolResponseContentEntity(
                author=MessageAuthor.AGENT,
                tool_call_id=self._accumulated_deltas[0].tool_call_id,
                name=self._accumulated_deltas[0].name,
                content=tool_response_content_str,
            )
        elif self._delta_type == DeltaType.REASONING_CONTENT:
            reasoning_content_str = "".join(
                [
                    delta.content_delta
                    for delta in self._accumulated_deltas
                    if delta.content_delta is not None
                ]
            )
            return ReasoningContentEntity(
                author=MessageAuthor.AGENT,
                content=[reasoning_content_str],
            )
        elif self._delta_type == DeltaType.REASONING_SUMMARY:
            reasoning_summary_str = "".join(
                [
                    delta.summary_delta
                    for delta in self._accumulated_deltas
                    if delta.summary_delta is not None
                ]
            )
            return ReasoningContentEntity(
                author=MessageAuthor.AGENT,
                summary=[reasoning_summary_str],
            )
        else:
            raise ClientError(f"Unknown delta type: {self._delta_type}")


class AgentsACPUseCase(TaskMessageMixin):
    """
    Use case for handling agent API requests through JSON-RPC.
    """

    def __init__(
        self,
        agent_repository: DAgentRepository,
        acp_client: DAgentACPService,
        task_service: DAgentTaskService,
        task_message_service: DTaskMessageService,
        authorization_service: DAuthorizationService,
    ):
        self.agent_repository = agent_repository
        self.acp_client = acp_client
        self.task_service = task_service
        self.task_message_service = task_message_service
        self.authorization_service = authorization_service

    @staticmethod
    def _validate_rpc_method_for_acp_type(
        acp_type: ACPType,
        method: AgentRPCMethod,
    ) -> None:
        if acp_type not in ACP_TYPE_TO_ALLOWED_RPC_METHODS:
            raise ClientError(f"Unsupported Agent ACP type: {acp_type}")
        if not any(
            method.value == allowed_method.value
            for allowed_method in ACP_TYPE_TO_ALLOWED_RPC_METHODS[acp_type]
        ):
            raise ClientError(f"Unsupported method: {method} for ACP type: {acp_type}")

    @staticmethod
    def is_streaming_request(request: AgentRPCRequestEntity) -> bool:
        """Check if the request is a streaming request"""
        return (
            request.method == AgentRPCMethod.MESSAGE_SEND
            and isinstance(request.params, SendMessageRequestEntity)
            and request.params.stream
        )

    """Handle synchronous message sending (existing logic)"""

    async def _execute_with_error_handling(
        self, task: TaskEntity, operation: Callable, error_message: str
    ):
        """Helper method to execute operations with consistent error handling"""
        try:
            return await operation()
        except Exception as e:
            logger.error(f"{error_message}: {e}")
            await self.task_service.fail_task(task, str(e))
            raise e

    async def _get_or_create_task(
        self,
        *,
        agent: AgentEntity,
        task_id: str | None = None,
        task_name: str | None = None,
        task_params: dict[str, Any] | None = None,
    ) -> TaskEntity:
        """Return the existing task if *task_id* is provided, otherwise create a new one.

        Note: Only one of task_id or task_name should be provided (enforced by validators).
        """

        # Get existing task by ID or name
        if task_id:
            task = await self.task_service.get_task(id=task_id)
        elif task_name:
            try:
                task = await self.task_service.get_task(name=task_name)
            except ItemDoesNotExist:
                # Task doesn't exist - will create below
                task = None
        else:
            # No identifier provided - will create below
            task = None

        # If task exists and params provided, update them
        if task and task_params is not None:
            if task.params != task_params:
                logger.info(
                    f"[agent_id={agent.id}] Updating params for task {task.id} "
                    f"from {task.params} to {task_params}"
                )
                task.params = task_params
                task = await self.task_service.update_task(task)
            return task

        # If task exists and no params provided, return as-is
        if task:
            return task

        # Create a new task if it doesn't exist
        task = await self.task_service.create_task(
            agent=agent, task_name=task_name, task_params=task_params
        )
        logger.info(f"[agent_id={agent.id}] Created task {task.id}")
        await self.authorization_service.grant(
            resource=AgentexResource.task(task.id),
        )
        return task

    async def handle_rpc_request(
        self,
        method: AgentRPCMethod,
        params: CreateTaskRequestEntity
        | CancelTaskRequestEntity
        | SendMessageRequestEntity
        | SendEventRequestEntity,
        agent_id: str | None = None,
        agent_name: str | None = None,
        request_headers: dict[str, str] | None = None,
    ) -> (
        list[TaskMessageEntity]
        | AsyncIterator[TaskMessageUpdateEntity]
        | TaskEntity
        | EventEntity
    ):
        """
        Handle JSON-RPC requests for an agent.

        Args:
            agent_id: ID of the agent to handle the request
            agent_name: Name of the agent to handle the request
            method: JSON-RPC method name
            params: JSON-RPC parameters
            request_id: JSON-RPC request ID
            request_headers: HTTP headers from the incoming request

        Returns:
            - list[TaskMessageEntity] for synchronous MESSAGE_SEND
            - AsyncIterator[TaskMessageUpdateEntity] for streaming MESSAGE_SEND
            - TaskEntity for TASK_CREATE or TASK_CANCEL
            - EventEntity for EVENT_SEND
        """
        # Get the agent
        agent = await self.agent_repository.get(id=agent_id, name=agent_name)
        if not agent.acp_url:
            raise ClientError(f"Agent {agent_id} does not have an ACP URL configured")
        if method not in AgentRPCMethod:
            raise ClientError(f"Unsupported method: {method}")

        logger.info(
            f"[handle_rpc_request] Validating RPC method for ACP type: {agent.acp_type} - {method}"
        )
        self._validate_rpc_method_for_acp_type(agent.acp_type, method)

        # Handle different methods
        if method == AgentRPCMethod.MESSAGE_SEND:
            return await self._handle_message_send(agent, params)
        elif method == AgentRPCMethod.TASK_CREATE:
            return await self._handle_task_create(agent, params)
        elif method == AgentRPCMethod.TASK_CANCEL:
            return await self._handle_task_cancel(agent, params)
        elif method == AgentRPCMethod.EVENT_SEND:
            return await self._handle_event_send(agent, params, request_headers)
        else:
            raise ValueError(f"Unsupported method: {method}")

    async def _handle_task_create(
        self, agent: AgentEntity, params: CreateTaskRequestEntity
    ) -> TaskEntity:
        """
        Handle task/create method.

        Args:
            agent: The agent to create the task for
            params: Parameters containing task and initial message

        Returns:
            Task containing the created task info
        """
        # This creates the task record then forwards the message to the ACP server
        task = await self._get_or_create_task(
            agent=agent, task_name=params.name, task_params=params.params
        )

        if agent.acp_type == ACPType.AGENTIC:
            await self.task_service.forward_task_to_acp(
                agent=agent,
                task=task,
                task_params=params.params,
            )
        return task

    async def _handle_message_send(
        self, agent: AgentEntity, params: SendMessageRequestEntity
    ) -> list[TaskMessageEntity] | AsyncIterator[TaskMessageUpdateEntity]:
        """
        Handle message/send method.

        Args:
            agent: The agent to send the message to
            params: Parameters containing task_id and message

        Returns:
            TaskMessageEntry for synchronous requests or AsyncIterator[TaskMessage] for streaming
        """
        if params.stream:
            return self._handle_message_send_stream(agent, params)
        else:
            return await self._handle_message_send_sync(agent, params)

    async def _handle_message_send_sync(
        self, agent: AgentEntity, params: SendMessageRequestEntity
    ) -> list[TaskMessageEntity]:
        task = await self._get_or_create_task(
            agent=agent,
            task_id=params.task_id,
            task_name=params.task_name,
            task_params=params.task_params,
        )

        # Step 1: Insert the message in the messages table
        await self._execute_with_error_handling(
            task=task,
            operation=lambda: self.task_message_service.append_message(
                task_id=task.id,
                content=params.content,
            ),
            error_message=f"Error appending input message to task {task.id}",
        )

        index_to_task_message_content_entities_to_create: dict[
            int, TaskMessageContentEntity
        ] = {}
        task_message_index_to_delta_accumulator: dict[int, DeltaAccumulator] = {}

        async def flush_aggregated_deltas(
            task_message_index: int,
        ) -> TaskMessageContentEntity | None:
            if task_message_index in index_to_task_message_content_entities_to_create:
                return index_to_task_message_content_entities_to_create[
                    task_message_index
                ]

            delta_accumulator = task_message_index_to_delta_accumulator.get(
                task_message_index
            )
            if not delta_accumulator or not delta_accumulator._accumulated_deltas:
                # No deltas to flush, return existing parent task message
                return index_to_task_message_content_entities_to_create.get(
                    task_message_index
                )

            full_content = delta_accumulator.convert_to_content()

            index_to_task_message_content_entities_to_create[task_message_index] = (
                full_content
            )
            return full_content

        async for task_message_update in self.task_service.send_message_stream(
            agent=agent,
            task=task,
            content=params.content,
            acp_url=agent.acp_url,
        ):
            logger.debug(
                f"[message_send_stream] Received message chunk: {task_message_update}"
            )

            # Get the index of the message chunk
            task_message_index = task_message_update.index

            if task_message_index is None:
                raise ClientError("Task message index is required")

            # If the message chunk index is in the completed_task_message_indexes and assume that the stream is done
            if task_message_index in index_to_task_message_content_entities_to_create:
                continue

            # Initialize delta accumulator for this index if not exists
            if task_message_index not in task_message_index_to_delta_accumulator:
                task_message_index_to_delta_accumulator[task_message_index] = (
                    DeltaAccumulator()
                )

            # If full, just write to the database, this is the final message
            if isinstance(task_message_update, StreamTaskMessageFullEntity):
                # Now, write to the database, the completed message for this index
                index_to_task_message_content_entities_to_create[task_message_index] = (
                    task_message_update.content
                )

            # If start, write an empty message to the database, deltas will be associated with this message later
            elif isinstance(task_message_update, StreamTaskMessageStartEntity):
                continue

            # If delta, add to the delta accumulator
            elif isinstance(task_message_update, StreamTaskMessageDeltaEntity):
                # Add delta to accumulator
                delta_accumulator = task_message_index_to_delta_accumulator[
                    task_message_index
                ]
                if task_message_update.delta:
                    delta_accumulator.add_delta(task_message_update.delta)
            elif isinstance(task_message_update, StreamTaskMessageDoneEntity):
                # Handle the done event by flushing accumulated deltas
                task_message_content_entity = task_message_index_to_delta_accumulator[
                    task_message_index
                ].convert_to_content()
                index_to_task_message_content_entities_to_create[task_message_index] = (
                    task_message_content_entity
                )

        ordered_task_message_content_entities_to_create: list[
            TaskMessageContentEntity
        ] = []
        for (
            task_message_index
        ) in index_to_task_message_content_entities_to_create.keys():
            flushed_content = await flush_aggregated_deltas(task_message_index)
            if flushed_content:
                ordered_task_message_content_entities_to_create.append(flushed_content)

        # Append the new task message result to the task
        new_task_message_entities: list[
            TaskMessageEntity
        ] = await self._execute_with_error_handling(
            task=task,
            operation=lambda: self.task_message_service.append_messages(
                task_id=task.id,
                contents=ordered_task_message_content_entities_to_create,
                streaming_status="DONE",
            ),
            error_message=f"Error appending response message to task {task.id}",
        )
        return new_task_message_entities

    async def _handle_message_send_stream(
        self, agent: AgentEntity, params: SendMessageRequestEntity
    ) -> AsyncIterator[TaskMessageUpdateEntity]:
        """Handle streaming message send - yields raw TaskMessage objects"""

        task = None
        task_message_index_to_delta_accumulator: dict[int, DeltaAccumulator] = {}
        completed_task_message_indexes = set()
        all_task_message_indexes = set()  # Use set to avoid duplicate memory usage

        task_message_index_to_parent_task_message: dict[int, TaskMessageEntity] = {}

        async def create_parent_task_message(
            task_message_index: int, content: TaskMessageContentEntity | None = None
        ) -> TaskMessageEntity:
            if task_message_index in task_message_index_to_parent_task_message:
                return task_message_index_to_parent_task_message[task_message_index]

            parent_task_message = await self.task_message_service.append_message(
                task_id=task.id,
                content=content,
            )
            task_message_index_to_parent_task_message[task_message_index] = (
                parent_task_message
            )
            return parent_task_message

        async def flush_aggregated_deltas(task_message_index: int) -> TaskMessageEntity:
            if task_message_index in completed_task_message_indexes:
                return task_message_index_to_parent_task_message[task_message_index]

            delta_accumulator = task_message_index_to_delta_accumulator.get(
                task_message_index
            )
            if not delta_accumulator or not delta_accumulator._accumulated_deltas:
                # No deltas to flush, return existing parent task message
                return task_message_index_to_parent_task_message.get(task_message_index)

            full_content = delta_accumulator.convert_to_content()

            if task_message_index not in task_message_index_to_parent_task_message:
                parent_task_message = await create_parent_task_message(
                    task_message_index=task_message_index,
                    content=full_content,
                )
            else:
                parent_task_message = await self.task_message_service.update_message(
                    task_id=task.id,
                    message_id=task_message_index_to_parent_task_message[
                        task_message_index
                    ].id,
                    content=full_content,
                    streaming_status="DONE",
                )
                task_message_index_to_parent_task_message[task_message_index] = (
                    parent_task_message
                )
            return parent_task_message

        try:
            # Setup task and initial message
            task = await self._get_or_create_task(
                agent=agent,
                task_id=params.task_id,
                task_name=params.task_name,
                task_params=params.task_params,
            )

            # Append the input client message
            await self.task_message_service.append_message(
                task_id=task.id,
                content=params.content,
                streaming_status="DONE",
            )
            # Stream the response - yield raw TaskMessage objects
            async for task_message_update in self.task_service.send_message_stream(
                agent=agent,
                task=task,
                content=params.content,
                acp_url=agent.acp_url,
            ):
                logger.debug(
                    f"[message_send_stream] Received message chunk type: {type(task_message_update).__name__}"
                )

                # Get the index of the message chunk
                task_message_index = task_message_update.index
                all_task_message_indexes.add(task_message_index)
                # If the message chunk index is in the completed_task_message_indexes and assume that the stream is done
                if task_message_index in completed_task_message_indexes:
                    continue

                # Initialize delta accumulator for this index if not exists
                if task_message_index not in task_message_index_to_delta_accumulator:
                    task_message_index_to_delta_accumulator[task_message_index] = (
                        DeltaAccumulator()
                    )

                # If full, just write to the database, this is the final message
                if isinstance(task_message_update, StreamTaskMessageFullEntity):
                    # Now, write to the database, the completed message for this index

                    if task_message_index in task_message_index_to_parent_task_message:
                        parent_task_message = task_message_index_to_parent_task_message[
                            task_message_index
                        ]
                        await self.task_message_service.update_message(
                            task_id=task.id,
                            message_id=parent_task_message.id,
                            content=task_message_update.content,
                            streaming_status="DONE",
                        )
                    else:
                        # Initialize the parent task message
                        parent_task_message = await create_parent_task_message(
                            task_message_index=task_message_index,
                            content=task_message_update.content,
                        )
                    task_message_update.parent_task_message = parent_task_message
                    # Mark the task message index as completed
                    completed_task_message_indexes.add(task_message_index)

                    logger.info(
                        f"[message_send_stream][full]: messageId={parent_task_message.id}, index={task_message_index}. content={task_message_update.content}"
                    )

                # If start, write an empty message to the database, deltas will be associated with this message later
                elif isinstance(task_message_update, StreamTaskMessageStartEntity):
                    parent_task_message = await create_parent_task_message(
                        task_message_index=task_message_index,
                        content=task_message_update.content,
                    )
                    task_message_update.parent_task_message = parent_task_message
                # If delta, add to the delta accumulator
                elif isinstance(task_message_update, StreamTaskMessageDeltaEntity):
                    # Check if this is the first delta for this message index
                    if (
                        task_message_index
                        not in task_message_index_to_parent_task_message
                    ):
                        # This is the first delta - send START message first
                        initial_content = self.create_initial_content_from_delta(
                            delta=task_message_update.delta
                        )
                        parent_task_message = await create_parent_task_message(
                            task_message_index=task_message_index,
                            content=initial_content,
                        )

                        logger.debug(
                            f"[message_send_stream][start]: messageId={parent_task_message.id}, index={task_message_index}. content={initial_content}"
                        )
                        yield StreamTaskMessageStartEntity(
                            index=task_message_index,
                            content=initial_content,
                            parent_task_message=parent_task_message,
                        )

                    # Add delta to accumulator
                    delta_accumulator = task_message_index_to_delta_accumulator[
                        task_message_index
                    ]
                    if task_message_update.delta:
                        delta_accumulator.add_delta(task_message_update.delta)

                    # Get the parent task message for this delta
                    parent_task_message = task_message_index_to_parent_task_message[
                        task_message_index
                    ]
                    task_message_update.parent_task_message = parent_task_message
                    logger.debug(
                        f"[message_send_stream][delta]: messageId={parent_task_message.id}, index={task_message_index}"
                    )
                elif isinstance(task_message_update, StreamTaskMessageDoneEntity):
                    # Handle the done event by flushing accumulated deltas
                    parent_task_message = await flush_aggregated_deltas(
                        task_message_index=task_message_index
                    )
                    task_message_update.parent_task_message = parent_task_message
                    completed_task_message_indexes.add(task_message_index)

                yield task_message_update
        except Exception as e:
            logger.error(f"Error in streaming message send: {e}")
            if task:
                await self.task_service.fail_task(task, str(e))
            # Re-raise the exception to let the routes layer handle error formatting
            raise

        # Now, the stream has concluded, we should attempt to flush any remaining deltas
        for task_message_index in all_task_message_indexes:
            await flush_aggregated_deltas(task_message_index=task_message_index)

        # Clear accumulated data to free memory
        task_message_index_to_delta_accumulator.clear()
        completed_task_message_indexes.clear()
        all_task_message_indexes.clear()
        task_message_index_to_parent_task_message.clear()
        return

    async def _handle_task_cancel(
        self, agent: AgentEntity, params: CancelTaskRequestEntity
    ) -> TaskEntity:
        """
        Handle task/cancel method.

        Args:
            agent: The agent to cancel the task for
            params: Parameters containing task_id

        Returns:
            Dict containing the cancellation result
        """

        task = await self.task_service.get_task(
            id=params.task_id, name=params.task_name
        )

        return await self.task_service.cancel_task(
            agent=agent,
            task=task,
            acp_url=agent.acp_url,
        )

    async def _handle_event_send(
        self,
        agent: AgentEntity,
        params: SendEventRequestEntity,
        request_headers: dict[str, str] | None = None,
    ) -> EventEntity:
        """
        Handle event/send method

        Args:
            agent: The agent to send the event to
            params: Parameters containing task_id and event data
            request_headers: HTTP headers from the incoming request

        Returns:
            EventEntity for the created and forwarded event
        """

        if not params.task_id and not params.task_name:
            raise ClientError("Either task_id or task_name must be provided")

        task = await self.task_service.get_task(
            id=params.task_id, name=params.task_name
        )
        # Create the event in the DB
        event_entity = await self.task_service.create_event_and_forward_to_acp(
            agent=agent,
            task=task,
            content=params.content,
            acp_url=agent.acp_url,
            request_headers=request_headers,
        )
        return event_entity


DAgentsACPUseCase = Annotated[AgentsACPUseCase, Depends(AgentsACPUseCase)]
