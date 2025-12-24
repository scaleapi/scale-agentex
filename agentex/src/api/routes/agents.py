import secrets
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.cache import cacheable
from src.api.schemas.agents import Agent, RegisterAgentRequest, RegisterAgentResponse
from src.api.schemas.agents_rpc import (
    AgentRPCRequest,
    AgentRPCResponse,
)
from src.api.schemas.authorization_types import (
    AgentexResource,
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.api.schemas.delete_response import DeleteResponse
from src.domain.entities.agent_api_keys import AgentAPIKeyType
from src.domain.entities.agents_rpc import (
    AgentRPCMethod,
    AgentRPCRequestEntity,
    SendMessageRequestEntity,
)
from src.domain.entities.json_rpc import JSONRPCError
from src.domain.services.authorization_service import (
    AuthorizationService,
    DAuthorizationService,
)
from src.domain.services.task_service import DAgentTaskService
from src.domain.use_cases.agent_api_keys_use_case import DAgentAPIKeysUseCase
from src.domain.use_cases.agents_acp_use_case import DAgentsACPUseCase
from src.domain.use_cases.agents_use_case import DAgentsUseCase
from src.utils.authorization_shortcuts import (
    DAuthorizedId,
    DAuthorizedName,
    DAuthorizedResourceIds,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get(
    "/{agent_id}",
    summary="Get Agent by ID",
    response_model=Agent,
    description="Get an agent by its unique ID.",
)
@cacheable(max_age=60)
async def get_agent_by_id(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.read),  # type: ignore
    agents_use_case: DAgentsUseCase,
    response: Response,
):
    """Get an agent by its unique ID."""
    agent_entity = await agents_use_case.get(id=agent_id)
    return Agent.model_validate(agent_entity)


@router.get(
    "/name/{agent_name}",
    response_model=Agent,
    summary="Get Agent by Name",
    description="Get an agent by its unique name.",
)
@cacheable(max_age=60)
async def get_agent_by_name(
    agent_name: DAuthorizedName(
        AgentexResourceType.agent, AuthorizedOperationType.read
    ),
    agents_use_case: DAgentsUseCase,
    authorization: DAuthorizationService,
    response: Response,
):
    """Get an agent by its unique name."""
    agent_entity = await agents_use_case.get(name=agent_name)

    await authorization.check(
        resource=AgentexResource.agent(agent_entity.id),
        operation=AuthorizedOperationType.read,
    )

    return Agent.model_validate(agent_entity)


@router.get(
    "",
    response_model=list[Agent],
    summary="List Agents",
    description="List all registered agents, optionally filtered by query parameters.",
)
@cacheable(max_age=60)
async def list_agents(
    agents_use_case: DAgentsUseCase,
    _authorized_ids: DAuthorizedResourceIds(AgentexResourceType.agent),
    response: Response,
    task_id: str | None = Query(None, description="Task ID"),
    limit: int = Query(50, description="Limit", ge=1),
    page_number: int = Query(1, description="Page number", ge=1),
    order_by: str | None = Query(None, description="Field to order by"),
    order_direction: str = Query("desc", description="Order direction (asc or desc)"),
):
    """List all registered agents."""
    agent_entities = await agents_use_case.list(
        task_id=task_id,
        limit=limit,
        page_number=page_number,
        order_by=order_by,
        order_direction=order_direction,
        **{"id": _authorized_ids} if _authorized_ids is not None else {},
    )
    return [Agent.model_validate(agent_entity) for agent_entity in agent_entities]


@router.delete(
    "/{agent_id}",
    response_model=DeleteResponse,
    summary="Delete Agent by ID",
    description="Delete an agent by its unique ID.",
)
async def delete_agent_by_id(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.delete),
    agents_use_case: DAgentsUseCase,
    authorization: DAuthorizationService,
):
    """Delete an agent by its unique ID."""
    agent_entity = await agents_use_case.delete(id=agent_id)
    await authorization.revoke(
        resource=AgentexResource.agent(agent_entity.id),
    )
    return DeleteResponse(
        id=agent_id, message=f"Agent '{agent_id}' deleted successfully"
    )


@router.delete(
    "/name/{agent_name}",
    response_model=DeleteResponse,
    summary="Delete Agent by Name",
    description="Delete an agent by its unique name.",
)
async def delete_agent_by_name(
    agent_name: DAuthorizedName(
        AgentexResourceType.agent, AuthorizedOperationType.delete
    ),  # type: ignore
    agents_use_case: DAgentsUseCase,
    authorization: DAuthorizationService,
):
    """Delete an agent by its unique name."""
    agent_entity = await agents_use_case.delete(name=agent_name)
    await authorization.revoke(
        resource=AgentexResource.agent(agent_entity.id),
    )
    return DeleteResponse(
        id=agent_entity.id, message=f"Agent '{agent_name}' deleted successfully"
    )


@router.post(
    "/register",
    response_model=RegisterAgentResponse,
    summary="Register Agent",
    description="Register a new agent or update an existing one.",
)
async def register_agent(
    request: RegisterAgentRequest,
    agents_use_case: DAgentsUseCase,
    authorization_service: DAuthorizationService,
    api_keys_use_case: DAgentAPIKeysUseCase,
) -> RegisterAgentResponse:
    """
    Register an agent with the platform. This endpoint allows agents to register themselves
    and is idempotent to handle multiple pods of the same agent registering simultaneously.

    If agent_id is provided, the agent with that ID will be updated with the new name/description.
    If agent_id is not provided, the system will look for an existing agent by name and update it,
    or create a new one if it doesn't exist.
    """
    await authorization_service.check(
        AgentexResource.agent("*"),
        AuthorizedOperationType.create,
        principal_context=request.principal_context,
    )
    logger.info(f"Registering agent: {request}")
    try:
        agent_entity = await agents_use_case.register_agent(
            name=request.name,
            description=request.description,
            acp_url=request.acp_url,
            agent_id=request.agent_id,
            acp_type=request.acp_type,
            registration_metadata=request.registration_metadata,
            agent_input_type=request.agent_input_type,
        )
        await authorization_service.grant(
            AgentexResource.agent(agent_entity.id),
            principal_context=request.principal_context,
        )
        response_fields = agent_entity.model_dump()
        existing_key = await api_keys_use_case.get_internal_api_key_by_agent_id(
            agent_id=agent_entity.id
        )
        if existing_key:
            response_fields["agent_api_key"] = existing_key.api_key
        else:
            # Create a new internal API key for the agent
            logger.info(f"Creating internal API key for agent {agent_entity.id}")
            new_api_key = secrets.token_hex(32)
            await api_keys_use_case.create(
                name=f"{agent_entity.name}-api-key",
                agent_id=agent_entity.id,
                api_key_type=AgentAPIKeyType.INTERNAL,
                api_key=new_api_key,
            )
            response_fields["agent_api_key"] = new_api_key
        return RegisterAgentResponse.model_validate(response_fields)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.api_route(
    "/forward/name/{agent_name}/{path:path}",
    methods=["GET", "POST"],
    summary="Forward request to agent by ID",
    description="Forward a request to an agent by its unique ID.",
)
async def forward_request_to_agent(
    agent_name: str,
    path: str,
    request: Request,
    agent_api_keys_use_case: DAgentAPIKeysUseCase,
):
    return await agent_api_keys_use_case.forward_agent_request(
        agent_name=agent_name,
        path=path,
        request=request,
    )


@router.post(
    "/{agent_id}/rpc",
    summary="Handle Agent RPC by ID",
    description="Handle JSON-RPC requests for an agent by its unique ID.",
    response_model=AgentRPCResponse,
)
async def handle_agent_rpc_by_id(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.execute),  # type: ignore
    request: AgentRPCRequest,
    fastapi_request: Request,
    agents_acp_use_case: DAgentsACPUseCase,
    authorization_service: DAuthorizationService,
    task_service: DAgentTaskService,
) -> AgentRPCResponse | StreamingResponse:
    """Handle JSON-RPC requests for an agent by its unique ID."""
    agent_rpc_request_entity = AgentRPCRequestEntity.from_api_request(request)
    await _authorize_rpc_request(
        agent_rpc_request_entity, authorization_service, task_service
    )

    # Extract headers from FastAPI request
    headers = dict(fastapi_request.headers)

    return await _handle_agent_rpc(
        request=agent_rpc_request_entity,
        agents_acp_use_case=agents_acp_use_case,
        agent_id=agent_id,
        request_headers=headers,
    )


@router.post(
    "/name/{agent_name}/rpc",
    summary="Handle Agent RPC by Name",
    description="Handle JSON-RPC requests for an agent by its unique name.",
    response_model=AgentRPCResponse,
)
async def handle_agent_rpc_by_name(
    agent_name: DAuthorizedName(
        AgentexResourceType.agent, AuthorizedOperationType.execute
    ),
    request: AgentRPCRequest,
    fastapi_request: Request,
    agents_acp_use_case: DAgentsACPUseCase,
    authorization_service: DAuthorizationService,
    task_service: DAgentTaskService,
) -> AgentRPCResponse | StreamingResponse:
    """Handle JSON-RPC requests for an agent by its unique name."""
    agent_rpc_request_entity = AgentRPCRequestEntity.from_api_request(request)
    await _authorize_rpc_request(
        agent_rpc_request_entity, authorization_service, task_service
    )

    # Extract headers from FastAPI request
    headers = dict(fastapi_request.headers)

    return await _handle_agent_rpc(
        request=agent_rpc_request_entity,
        agents_acp_use_case=agents_acp_use_case,
        agent_name=agent_name,
        request_headers=headers,
    )


async def _authorize_rpc_request(
    request: AgentRPCRequestEntity,
    authorization_service: AuthorizationService,
    task_service: DAgentTaskService,
):
    match request.method:
        case AgentRPCMethod.TASK_CREATE:
            await authorization_service.check(
                resource=AgentexResource.task("*"),
                operation=AuthorizedOperationType.create,
            )

        case AgentRPCMethod.MESSAGE_SEND:
            task_id = request.params.task_id
            task_name = request.params.task_name

            if task_id is not None:
                # Direct task ID provided - check execute permission on that specific task
                await authorization_service.check(
                    resource=AgentexResource.task(task_id),
                    operation=AuthorizedOperationType.execute,
                )
            elif task_name is not None:
                # Task name provided - check if task exists
                try:
                    existing_task = await task_service.get_task(name=task_name)
                    # Task exists - require execute permission on the specific task
                    await authorization_service.check(
                        resource=AgentexResource.task(existing_task.id),
                        operation=AuthorizedOperationType.execute,
                    )
                except ItemDoesNotExist:
                    # Task doesn't exist - will be created, require create permission
                    await authorization_service.check(
                        resource=AgentexResource.task("*"),
                        operation=AuthorizedOperationType.create,
                    )
            else:
                # No identifier provided - creating new task, require create permission
                await authorization_service.check(
                    resource=AgentexResource.task("*"),
                    operation=AuthorizedOperationType.create,
                )

        case AgentRPCMethod.EVENT_SEND:
            task_id = request.params.task_id
            task_name = request.params.task_name

            if task_id is not None:
                # Direct task ID provided - check execute permission on that specific task
                await authorization_service.check(
                    resource=AgentexResource.task(task_id),
                    operation=AuthorizedOperationType.execute,
                )
            elif task_name is not None:
                # Task name provided - look up task and check execute permission
                existing_task = await task_service.get_task(name=task_name)
                await authorization_service.check(
                    resource=AgentexResource.task(existing_task.id),
                    operation=AuthorizedOperationType.execute,
                )
            else:
                # No identifier provided - this shouldn't happen but handle gracefully
                raise ValueError(
                    "Either task_id or task_name must be provided for event/send"
                )

        case AgentRPCMethod.TASK_CANCEL:
            task_id = request.params.task_id
            task_name = request.params.task_name

            if task_id is not None:
                # Direct task ID provided - check execute permission on that specific task
                await authorization_service.check(
                    resource=AgentexResource.task(task_id),
                    operation=AuthorizedOperationType.execute,
                )
            elif task_name is not None:
                # Task name provided - look up task and check execute permission
                existing_task = await task_service.get_task(name=task_name)
                await authorization_service.check(
                    resource=AgentexResource.task(existing_task.id),
                    operation=AuthorizedOperationType.execute,
                )
            else:
                # No identifier provided - this shouldn't happen but handle gracefully
                raise ValueError(
                    "Either task_id or task_name must be provided for task/cancel"
                )
        case _:
            pass


async def _handle_agent_rpc(
    request: AgentRPCRequestEntity,
    agents_acp_use_case: DAgentsACPUseCase,
    agent_id: str | None = None,
    agent_name: str | None = None,
    request_headers: dict[str, str] | None = None,
) -> AgentRPCResponse | StreamingResponse:
    """Handle JSON-RPC requests for an agent by its unique ID or name."""

    # Check if this is a streaming request
    is_streaming_request = (
        request.method == AgentRPCMethod.MESSAGE_SEND
        and isinstance(request.params, SendMessageRequestEntity)
        and request.params.stream
    )

    logger.info(f"Is streaming request: {is_streaming_request}")
    logger.info(f"Request: {request}")

    if is_streaming_request:
        return await _handle_streaming_rpc(
            request, agents_acp_use_case, agent_id, agent_name, request_headers
        )
    else:
        return await _handle_sync_rpc(
            request, agents_acp_use_case, agent_id, agent_name, request_headers
        )


async def _handle_sync_rpc(
    request: AgentRPCRequestEntity,
    agents_acp_use_case: DAgentsACPUseCase,
    agent_id: str | None = None,
    agent_name: str | None = None,
    request_headers: dict[str, str] | None = None,
) -> AgentRPCResponse:
    """Handle synchronous JSON-RPC requests."""
    try:
        result_entity = await agents_acp_use_case.handle_rpc_request(
            agent_id=agent_id,
            agent_name=agent_name,
            method=request.method,
            params=request.params,
            request_headers=request_headers,
        )

        if isinstance(result_entity, AsyncIterator):
            raise ValueError(f"Expected non-async iterator, got {type(result_entity)}")

        if isinstance(result_entity, list):
            serialized_result = [item.model_dump() for item in result_entity]
        else:
            serialized_result = result_entity.model_dump()

        # if request.method == AgentRPCMethod.MESSAGE_SEND:
        #     if isinstance(result_entity, list):
        #         result = [TaskMessage.model_validate(task_message_entity) for task_message_entity in result_entity]
        #     else:
        #         raise ValueError(f"Expected list of TaskMessage entities, got {type(result_entity)}")
        # elif request.method == AgentRPCMethod.TASK_CREATE:
        #     result = Task.model_validate(result_entity)
        # elif request.method == AgentRPCMethod.TASK_CANCEL:
        #     result = Task.model_validate(result_entity)
        # elif request.method == AgentRPCMethod.EVENT_SEND:
        #     result = Event.model_validate(result_entity)
        # else:
        #     raise ValueError(f"Unsupported method: {request.method}")
        # logger.info(f"AgentRPCResponse Result: {result}")
        return AgentRPCResponse.model_validate(
            {
                "id": request.id,
                "result": serialized_result,
                "error": None,
            }
        )

    except ValidationError as e:
        logger.error(f"Validation error in RPC request: {e}", exc_info=True)
        error = JSONRPCError(code=-32602, message=f"Invalid parameters: {e}")
        return AgentRPCResponse(id=request.id, error=error.model_dump(), result=None)
    except Exception as e:
        logger.error(f"Error handling JSON-RPC request: {e}", exc_info=True)
        error = JSONRPCError(code=-32603, message=str(e))
        return AgentRPCResponse(id=request.id, error=error.model_dump(), result=None)


async def _handle_streaming_rpc(
    request: AgentRPCRequestEntity,
    agents_acp_use_case: DAgentsACPUseCase,
    agent_id: str | None = None,
    agent_name: str | None = None,
    request_headers: dict[str, str] | None = None,
) -> StreamingResponse:
    """Handle streaming JSON-RPC requests."""

    async def rpc_response_generator():
        result_entity_async_iterator = None
        try:
            result_entity_async_iterator = await agents_acp_use_case.handle_rpc_request(
                agent_id=agent_id,
                agent_name=agent_name,
                method=request.method,
                params=request.params,
                request_headers=request_headers,
            )

            if not isinstance(result_entity_async_iterator, AsyncIterator):
                raise ValueError(
                    f"Expected AsyncIterator, got {type(result_entity_async_iterator)}"
                )

            # At this point we know it's an AsyncIterator[TaskMessage]
            async for task_message_update_entity in result_entity_async_iterator:
                logger.debug(
                    f"Streaming message chunk type: {type(task_message_update_entity).__name__}"
                )
                rpc_response = AgentRPCResponse.model_validate(
                    {
                        "id": request.id,
                        "result": task_message_update_entity.model_dump(),
                        "error": None,
                    }
                )
                # Yield JSON bytes with newline for NDJSON format
                yield rpc_response.model_dump_json().encode() + b"\n"

        except Exception as e:
            logger.error(f"Error in streaming RPC response: {e}", exc_info=True)
            # Yield error response
            error_response = AgentRPCResponse(
                id=request.id,
                result=None,
                error=JSONRPCError(code=-32603, message=str(e)).model_dump(),
            )
            yield error_response.model_dump_json().encode() + b"\n"
        finally:
            # CRITICAL: Ensure the async iterator is properly closed
            # This ensures HTTP connections are released back to the pool
            if result_entity_async_iterator is not None and hasattr(
                result_entity_async_iterator, "aclose"
            ):
                try:
                    await result_entity_async_iterator.aclose()
                    logger.debug("Closed streaming iterator properly")
                except Exception as e:
                    logger.warning(f"Error closing streaming iterator: {e}")

    return StreamingResponse(
        rpc_response_generator(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
