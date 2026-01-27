import os
from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends
from pydantic import BaseModel

from src.adapters.http.adapter_httpx import DHttpxGateway
from src.domain.entities.agents import AgentEntity
from src.domain.entities.agents_rpc import (
    AgentRPCMethod,
    CancelTaskParams,
    CreateTaskParams,
    SendEventParams,
    SendMessageParams,
)
from src.domain.entities.events import EventEntity
from src.domain.entities.json_rpc import JSONRPCRequest, JSONRPCResponse
from src.domain.entities.task_message_updates import (
    StreamTaskMessageDeltaEntity,
    StreamTaskMessageDoneEntity,
    StreamTaskMessageFullEntity,
    StreamTaskMessageStartEntity,
    TaskMessageUpdateEntity,
    TaskMessageUpdateType,
)

# TaskMessage is a discriminated union, so we need to validate based on the type field
from src.domain.entities.task_messages import (
    DataContentEntity,
    TaskMessageContentEntity,
    TaskMessageContentType,
    TextContentEntity,
    ToolRequestContentEntity,
    ToolResponseContentEntity,
)
from src.domain.entities.tasks import TaskEntity
from src.domain.mixins.task_messages.task_message_mixin import TaskMessageMixin
from src.domain.repositories.agent_api_key_repository import DAgentAPIKeyRepository
from src.domain.repositories.agent_repository import DAgentRepository
from src.utils.logging import ctx_var_request_id, make_logger

logger = make_logger(__name__)


USE_STREAMING_ADVISORY_LOCK = os.environ.get(
    "USE_STREAMING_ADVISORY_LOCK", "false"
) in ["true", "1", "yes"]

# Hop-by-hop headers that should not be forwarded to downstream services
# https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers#hop-by-hop_headers
HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "content-length",
        "content-encoding",
        "host",
    }
)

# Sensitive headers that should never be forwarded from client requests
# to prevent credential spoofing or leaking
BLOCKED_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "x-agent-api-key",
    }
)


def filter_request_headers(headers: dict[str, str] | None) -> dict[str, str]:
    """
    Filter request headers to only include safe custom headers.

    Security filtering rules:
    1. Allow only x-* prefixed headers (allowlist approach)
    2. Block hop-by-hop headers (connection, keep-alive, etc.)
    3. Block sensitive headers (authorization, cookie, x-agent-api-key)

    Args:
        headers: Raw request headers from client

    Returns:
        Filtered headers safe to forward to downstream agents
    """
    if not headers:
        return {}

    # Note: HOP_BY_HOP_HEADERS check is defensive programming - while it currently
    # contains no x-* headers, this ensures future-proof filtering if custom hop-by-hop
    # headers are added (e.g., x-custom-connection-option)
    return {
        k: v
        for k, v in headers.items()
        if k.lower().startswith("x-")
        and k.lower() not in HOP_BY_HOP_HEADERS
        and k.lower() not in BLOCKED_HEADERS
    }


class AgentACPService(TaskMessageMixin):
    """
    Client service for communicating with downstream ACP servers.
    Handles JSON-RPC 2.0 communication with agent ACP servers.
    """

    def __init__(
        self,
        agent_repository: DAgentRepository,
        agent_api_key_repository: DAgentAPIKeyRepository,
        http_gateway: DHttpxGateway,
    ):
        self._http_gateway = http_gateway
        self._agent_repository = agent_repository
        self._agent_api_key_repository = agent_api_key_repository

    def _parse_task_message(self, result: dict[str, Any]) -> TaskMessageContentEntity:
        """Parse a result dict into a TaskMessage"""
        try:
            message_type = result.get("type")
            if message_type == TaskMessageContentType.TEXT:
                return TextContentEntity.model_validate(result)
            elif message_type == TaskMessageContentType.DATA:
                return DataContentEntity.model_validate(result)
            elif message_type == TaskMessageContentType.TOOL_REQUEST:
                return ToolRequestContentEntity.model_validate(result)
            elif message_type == TaskMessageContentType.TOOL_RESPONSE:
                return ToolResponseContentEntity.model_validate(result)
            else:
                raise ValueError(f"Unknown message type: {message_type}")
        except Exception as e:
            logger.error(
                f"Failed to validate ACP response as TaskMessage. Result: {result} - Error: {e}"
            )
            if hasattr(e, "errors"):
                logger.error(f"Validation error details: {e.errors()}")
            raise ValueError(
                f"ACP server returned invalid TaskMessage format: {str(e)}"
            ) from e

    def _parse_task_message_update(
        self, result: dict[str, Any]
    ) -> TaskMessageUpdateEntity:
        """Parse a result dict into a TaskMessageUpdate"""
        update_type = result.get("type")
        if update_type == TaskMessageUpdateType.START:
            return StreamTaskMessageStartEntity.model_validate(result)
        elif update_type == TaskMessageUpdateType.DELTA:
            return StreamTaskMessageDeltaEntity.model_validate(result)
        elif update_type == TaskMessageUpdateType.FULL:
            return StreamTaskMessageFullEntity.model_validate(result)
        elif update_type == TaskMessageUpdateType.DONE:
            return StreamTaskMessageDoneEntity.model_validate(result)
        else:
            raise ValueError(f"Unknown update type: {update_type}")

    async def _call_jsonrpc(
        self,
        url: str,
        method: AgentRPCMethod,
        params: BaseModel,
        request_id: int | str | None = 1,
        default_headers: dict | None = None,
    ) -> dict[str, Any]:
        """
        Make a JSON-RPC 2.0 call to the ACP server.

        Args:
            url: The ACP server URL
            method: The RPC method name
            params: The method parameters as a Pydantic model
            request_id: Optional request ID. If None, the request is treated as a notification.
        """
        request = JSONRPCRequest(
            method=method, params=params.model_dump(mode="json"), id=request_id
        )
        try:
            response = await self._http_gateway.async_call(
                method="POST",
                url=f"{url}/api",
                payload=request.model_dump(),
                timeout=60,
                default_headers=default_headers,
            )

            if request_id is None:
                # This was a notification, no response expected
                return {}

            rpc_response = JSONRPCResponse.model_validate(response)

            # Verify the response ID matches our request ID
            if rpc_response.id != request_id:
                raise ValueError(
                    f"Response ID {rpc_response.id} does not match request ID {request_id}"
                )

            if rpc_response.error:
                raise ValueError(f"RPC error: {rpc_response.error}")

            return rpc_response.result or {}

        except Exception as e:
            logger.error(f"Error calling ACP server at {url}: {e}")
            raise e

    async def _call_jsonrpc_stream(
        self,
        url: str,
        method: AgentRPCMethod,
        params: BaseModel,
        request_id: int | str | None = 1,
        default_headers: dict | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Make a streaming JSON-RPC 2.0 call to the ACP server"""
        request = JSONRPCRequest(
            method=method, params=params.model_dump(mode="json"), id=request_id
        )

        try:
            logger.info(
                "Calling model dump on payload:", request.model_dump(mode="json")
            )
            payload = request.model_dump(mode="json")
            # logger.info(f"Streaming payload: {payload}")
            async for chunk in self._http_gateway.stream_call(
                method="POST",
                url=f"{url}/api",
                payload=payload,
                default_headers=default_headers,
            ):
                rpc_response = JSONRPCResponse.model_validate(chunk)

                # Verify the response ID matches our request ID
                if rpc_response.id != request_id:
                    raise ValueError(
                        f"Response ID {rpc_response.id} does not match request ID {request_id}"
                    )

                if rpc_response.error:
                    raise ValueError(f"RPC error: {rpc_response.error}")

                yield rpc_response.result or {}
        except Exception as e:
            logger.error(f"Error calling ACP server at {url}: {e}")
            raise e

    async def get_headers(self, agent: AgentEntity) -> dict[str, str]:
        auth_headers = await self.get_agent_auth_headers(agent) or {}

        request_id = ctx_var_request_id.get(uuid4().hex)
        headers = {**auth_headers, "x-request-id": request_id}
        return headers

    async def get_agent_auth_headers(
        self,
        agent: AgentEntity,
    ) -> dict[str, str] | None:
        """
        Get the authentication headers for an agent by its ID.
        """
        api_key = await self._agent_api_key_repository.get_internal_api_key_by_agent_id(
            agent_id=agent.id
        )
        if api_key:
            return {"x-agent-api-key": api_key.api_key}
        return None

    async def create_task(
        self,
        agent: AgentEntity,
        task: TaskEntity,
        acp_url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new task"""
        params = CreateTaskParams(
            agent=agent,
            task=task,
            params=params,
        )
        headers = await self.get_headers(agent)
        return await self._call_jsonrpc(
            url=acp_url,
            method=AgentRPCMethod.TASK_CREATE,
            params=params,
            request_id=f"{AgentRPCMethod.TASK_CREATE}-{task.id}",  # Use create-specific request ID
            default_headers=headers,
        )

    async def send_message(
        self,
        agent: AgentEntity,
        task: TaskEntity,
        content: TaskMessageContentEntity,
        acp_url: str,
    ) -> TaskMessageContentEntity:
        """Send a message to a running task"""
        params = SendMessageParams(
            agent=agent,
            task=task,
            content=content,
            stream=False,
        )
        headers = await self.get_headers(agent)
        lock_key = hash((agent.id, task.id))
        async with self._agent_repository.acquire_advisory_lock(lock_key) as acquired:
            if not acquired:
                raise ValueError(
                    f"Agent {agent.id} already processing message send for task {task.id}"
                )
            result = await self._call_jsonrpc(
                url=acp_url,
                method=AgentRPCMethod.MESSAGE_SEND,
                params=params,
                request_id=f"{AgentRPCMethod.MESSAGE_SEND}-{task.id}",  # Use message-specific request ID
                default_headers=headers,
            )

            return self._parse_task_message(result)

    async def send_message_stream(
        self,
        agent: AgentEntity,
        task: TaskEntity,
        content: TaskMessageContentEntity,
        acp_url: str,
    ) -> AsyncIterator[TaskMessageUpdateEntity]:
        """Send a message to a running task and stream the response"""
        params = SendMessageParams(
            agent=agent,
            task=task,
            content=content,
            stream=True,
        )
        headers = await self.get_headers(agent)
        lock_key = hash((agent.id, task.id))

        if USE_STREAMING_ADVISORY_LOCK:
            # Old behavior: Hold advisory lock for entire stream duration
            # WARNING: This holds a DB connection for 10+ seconds per stream!
            # With limited DB pool size, this can cause bottlenecks at high concurrency
            async with self._agent_repository.acquire_advisory_lock(
                lock_key
            ) as acquired:
                if not acquired:
                    raise ValueError(
                        f"Agent {agent.id} already processing message send for task {task.id}"
                    )
                async for chunk in self._call_jsonrpc_stream(
                    url=acp_url,
                    method=AgentRPCMethod.MESSAGE_SEND,
                    params=params,
                    request_id=f"{AgentRPCMethod.MESSAGE_SEND}-{task.id}",
                    default_headers=headers,
                ):
                    yield self._parse_task_message_update(chunk)
        else:
            async for chunk in self._call_jsonrpc_stream(
                url=acp_url,
                method=AgentRPCMethod.MESSAGE_SEND,
                params=params,
                request_id=f"{AgentRPCMethod.MESSAGE_SEND}-{task.id}",
                default_headers=headers,
            ):
                yield self._parse_task_message_update(chunk)

    async def cancel_task(
        self, agent: AgentEntity, task: TaskEntity, acp_url: str
    ) -> dict[str, Any]:
        """Cancel a running task"""
        params = CancelTaskParams(agent=agent, task=task)
        headers = await self.get_headers(agent)
        return await self._call_jsonrpc(
            url=acp_url,
            method=AgentRPCMethod.TASK_CANCEL,
            params=params,
            request_id=f"{AgentRPCMethod.TASK_CANCEL}-{task.id}",  # Use cancel-specific request ID
            default_headers=headers,
        )

    async def send_event(
        self,
        agent: AgentEntity,
        event: EventEntity,
        task: TaskEntity,
        acp_url: str,
        request_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send an event to a running task"""

        # Filter request headers for security (only safe x-* headers)
        filtered_headers = filter_request_headers(request_headers)

        # Don't include headers in params body - let SDK extract from HTTP headers
        # This ensures single source of truth and avoids duplication
        params = SendEventParams(
            agent=agent,
            task=task,
            event=event,
            request=None,
        )

        # Build HTTP headers: start with filtered request headers, then overlay auth headers
        # Auth headers are added last to ensure they cannot be overwritten
        # SDK will extract these headers and populate params.request at agent side
        headers = filtered_headers.copy()
        auth_headers = await self.get_headers(agent)
        headers.update(auth_headers)

        return await self._call_jsonrpc(
            url=acp_url,
            method=AgentRPCMethod.EVENT_SEND,
            params=params,
            request_id=f"{AgentRPCMethod.EVENT_SEND}-{task.id}",  # Use event-specific request ID
            default_headers=headers,
        )


DAgentACPService = Annotated[AgentACPService, Depends(AgentACPService)]
