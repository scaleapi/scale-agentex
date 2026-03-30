from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from src.api.schemas.agents_rpc import AgentRPCRequest, AgentRPCResponse
from src.api.schemas.authorization_types import (
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.api.schemas.delete_response import DeleteResponse
from src.api.schemas.deployments import CreateDeploymentRequest, Deployment
from src.domain.entities.agents_rpc import (
    AgentRPCMethod,
    AgentRPCRequestEntity,
    SendMessageRequestEntity,
)
from src.domain.entities.json_rpc import JSONRPCError
from src.domain.use_cases.agents_acp_use_case import DAgentsACPUseCase
from src.domain.use_cases.deployment_use_case import DDeploymentUseCase
from src.utils.authorization_shortcuts import DAuthorizedId
from src.utils.logging import make_logger

logger = make_logger(__name__)

router = APIRouter(
    prefix="/agents/{agent_id}/deployments",
    tags=["Deployments"],
)


@router.post(
    "",
    response_model=Deployment,
    summary="Create Deployment",
    description="Create a new deployment record in PENDING status.",
)
async def create_deployment(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.execute),
    request: CreateDeploymentRequest,
    deployment_use_case: DDeploymentUseCase,
) -> Deployment:
    deployment_entity = await deployment_use_case.create_deployment(
        agent_id=agent_id,
        docker_image=request.docker_image,
        commit_hash=request.commit_hash,
        branch_name=request.branch_name,
        author_name=request.author_name,
        author_email=request.author_email,
        sgp_deploy_id=request.sgp_deploy_id,
        helm_release_name=request.helm_release_name,
        build_timestamp=request.build_timestamp,
    )
    return Deployment.model_validate(deployment_entity)


@router.get(
    "",
    response_model=list[Deployment],
    summary="List Deployments",
    description="List deployments for an agent, newest first.",
)
async def list_deployments(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.read),
    deployment_use_case: DDeploymentUseCase,
    limit: int = Query(50, description="Limit", ge=1),
    page_number: int = Query(1, description="Page number", ge=1),
    order_by: str | None = Query(None, description="Field to order by"),
    order_direction: str = Query("desc", description="Order direction (asc or desc)"),
) -> list[Deployment]:
    deployment_entities = await deployment_use_case.list_deployments(
        agent_id=agent_id,
        limit=limit,
        page_number=page_number,
        order_by=order_by,
        order_direction=order_direction,
    )
    return [Deployment.model_validate(d) for d in deployment_entities]


@router.get(
    "/{deployment_id}",
    response_model=Deployment,
    summary="Get Deployment",
    description="Get a specific deployment by ID.",
)
async def get_deployment(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.read),
    deployment_id: str,
    deployment_use_case: DDeploymentUseCase,
) -> Deployment:
    deployment_entity = await deployment_use_case.get_deployment(
        deployment_id=deployment_id,
    )
    return Deployment.model_validate(deployment_entity)


@router.post(
    "/{deployment_id}/promote",
    response_model=Deployment,
    summary="Promote Deployment",
    description="Promote a deployment to production with atomic cutover.",
)
async def promote_deployment(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.execute),
    deployment_id: str,
    deployment_use_case: DDeploymentUseCase,
) -> Deployment:
    deployment_entity = await deployment_use_case.promote_deployment(
        agent_id=agent_id,
        deployment_id=deployment_id,
    )
    return Deployment.model_validate(deployment_entity)


@router.post(
    "/{deployment_id}/rollback",
    response_model=Deployment,
    summary="Rollback to Deployment",
    description="Rollback to a previous deployment (promotes it to production).",
)
async def rollback_deployment(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.execute),
    deployment_id: str,
    deployment_use_case: DDeploymentUseCase,
) -> Deployment:
    deployment_entity = await deployment_use_case.rollback_deployment(
        agent_id=agent_id,
        deployment_id=deployment_id,
    )
    return Deployment.model_validate(deployment_entity)


@router.delete(
    "/{deployment_id}",
    response_model=DeleteResponse,
    summary="Delete Deployment",
    description="Delete a non-production deployment.",
)
async def delete_deployment(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.delete),
    deployment_id: str,
    deployment_use_case: DDeploymentUseCase,
) -> DeleteResponse:
    await deployment_use_case.delete_deployment(
        agent_id=agent_id,
        deployment_id=deployment_id,
    )
    return DeleteResponse(
        id=deployment_id,
        message=f"Deployment '{deployment_id}' deleted successfully",
    )


@router.post(
    "/{deployment_id}/rpc",
    response_model=AgentRPCResponse,
    summary="Preview RPC",
    description="Send an RPC request to a specific deployment (for preview testing).",
)
async def handle_deployment_rpc(
    agent_id: DAuthorizedId(AgentexResourceType.agent, AuthorizedOperationType.execute),
    deployment_id: str,
    request: AgentRPCRequest,
    fastapi_request: Request,
    agents_acp_use_case: DAgentsACPUseCase,
    deployment_use_case: DDeploymentUseCase,
) -> AgentRPCResponse | StreamingResponse:
    deployment = await deployment_use_case.get_deployment(deployment_id=deployment_id)
    if not deployment.acp_url:
        raise ValueError(
            f"Deployment {deployment_id} does not have an ACP URL configured"
        )

    agent_rpc_request_entity = AgentRPCRequestEntity.from_api_request(request)
    headers = dict(fastapi_request.headers)

    is_streaming_request = (
        agent_rpc_request_entity.method == AgentRPCMethod.MESSAGE_SEND
        and isinstance(agent_rpc_request_entity.params, SendMessageRequestEntity)
        and agent_rpc_request_entity.params.stream
    )

    if is_streaming_request:
        return await _handle_deployment_streaming_rpc(
            agent_rpc_request_entity,
            agents_acp_use_case,
            agent_id,
            deployment.acp_url,
            headers,
        )
    else:
        return await _handle_deployment_sync_rpc(
            agent_rpc_request_entity,
            agents_acp_use_case,
            agent_id,
            deployment.acp_url,
            headers,
        )


async def _handle_deployment_sync_rpc(
    request: AgentRPCRequestEntity,
    agents_acp_use_case: DAgentsACPUseCase,
    agent_id: str,
    acp_url: str,
    request_headers: dict[str, str] | None = None,
) -> AgentRPCResponse:
    from collections.abc import AsyncIterator

    try:
        result_entity = await agents_acp_use_case.handle_rpc_request(
            agent_id=agent_id,
            method=request.method,
            params=request.params,
            request_headers=request_headers,
            acp_url_override=acp_url,
        )

        if isinstance(result_entity, AsyncIterator):
            raise ValueError(f"Expected non-async iterator, got {type(result_entity)}")

        if isinstance(result_entity, list):
            serialized_result = [item.model_dump() for item in result_entity]
        else:
            serialized_result = result_entity.model_dump()

        return AgentRPCResponse.model_validate(
            {"id": request.id, "result": serialized_result, "error": None}
        )
    except Exception as e:
        logger.error(f"Error handling deployment RPC request: {e}", exc_info=True)
        error = JSONRPCError(code=-32603, message=str(e))
        return AgentRPCResponse(id=request.id, error=error.model_dump(), result=None)


async def _handle_deployment_streaming_rpc(
    request: AgentRPCRequestEntity,
    agents_acp_use_case: DAgentsACPUseCase,
    agent_id: str,
    acp_url: str,
    request_headers: dict[str, str] | None = None,
) -> StreamingResponse:
    from collections.abc import AsyncIterator

    async def rpc_response_generator():
        result_entity_async_iterator = None
        try:
            result_entity_async_iterator = await agents_acp_use_case.handle_rpc_request(
                agent_id=agent_id,
                method=request.method,
                params=request.params,
                request_headers=request_headers,
                acp_url_override=acp_url,
            )

            if not isinstance(result_entity_async_iterator, AsyncIterator):
                raise ValueError(
                    f"Expected AsyncIterator, got {type(result_entity_async_iterator)}"
                )

            async for task_message_update_entity in result_entity_async_iterator:
                rpc_response = AgentRPCResponse.model_validate(
                    {
                        "id": request.id,
                        "result": task_message_update_entity.model_dump(),
                        "error": None,
                    }
                )
                yield rpc_response.model_dump_json().encode() + b"\n"

        except Exception as e:
            logger.error(
                f"Error in deployment streaming RPC response: {e}", exc_info=True
            )
            error_response = AgentRPCResponse(
                id=request.id,
                result=None,
                error=JSONRPCError(code=-32603, message=str(e)).model_dump(),
            )
            yield error_response.model_dump_json().encode() + b"\n"
        finally:
            if result_entity_async_iterator is not None and hasattr(
                result_entity_async_iterator, "aclose"
            ):
                try:
                    await result_entity_async_iterator.aclose()
                except Exception as e:
                    logger.warning(f"Error closing streaming iterator: {e}")

    return StreamingResponse(
        rpc_response_generator(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
