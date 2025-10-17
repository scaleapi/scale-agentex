from fastapi import APIRouter
from src.api.schemas.authorization_schemas import (
    AuthorizationResponse,
    CheckRequest,
    GrantRequest,
    ResourcesAuthorizationResponse,
    ResourcesRequest,
    RevokeRequest,
)
from src.domain.services.authorization_service import DAuthorizationService

authorization_router = APIRouter(tags=["authz"])


@authorization_router.post(
    "/v1/authz/grant",
    summary="Grant an operation to a principal on a resource",
    response_model=AuthorizationResponse,
)
async def grant_action(
    request: GrantRequest,
    service: DAuthorizationService,
) -> AuthorizationResponse:  # noqa: D401
    """Create a new (principal, resource, operation) edge."""
    await service.grant(
        principal=request.principal,
        resource=request.resource,
        operation=request.operation,
    )
    return AuthorizationResponse(success=True)


@authorization_router.post(
    "/v1/authz/revoke",
    summary="Revoke an operation from a principal on a resource",
    response_model=AuthorizationResponse,
)
async def revoke_action(
    request: RevokeRequest,
    service: DAuthorizationService,
) -> AuthorizationResponse:  # noqa: D401
    """Delete an existing (principal, resource, operation) edge."""
    await service.revoke(
        principal=request.principal,
        resource=request.resource,
        operation=request.operation,
    )
    return AuthorizationResponse(success=True)


@authorization_router.post(
    "/v1/authz/check",
    summary="Check whether a principal holds an operation on a resource",
    response_model=AuthorizationResponse,
)
async def check_action(
    request: CheckRequest,
    service: DAuthorizationService,
) -> AuthorizationResponse:  # noqa: D401
    """Return *True* iff *principal* has *operation* on *resource*."""
    await service.check(
        principal=request.principal,
        resource=request.resource,
        operation=request.operation,
    )
    return AuthorizationResponse(success=True)


@authorization_router.post(
    "/v1/authz/search",
    summary="List resources available to principal",
    response_model=ResourcesAuthorizationResponse,
)
async def list_resources(
    request: ResourcesRequest,
    service: DAuthorizationService,
) -> ResourcesAuthorizationResponse:  # noqa: D401
    items = await service.list_resources(
        principal=request.principal,
        filter_resource=request.filter_resource,
        filter_operation=request.filter_operation,
    )
    return ResourcesAuthorizationResponse(items=items)
