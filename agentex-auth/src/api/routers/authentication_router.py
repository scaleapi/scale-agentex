from fastapi import APIRouter, Request
from src.api.schemas.principal_context import PrincipalContext
from src.domain.services.authentication_service import DAuthenticationService

authentication_router = APIRouter(tags=["authn"])


@authentication_router.post(
    "/v1/authn",
    summary="Authenticate",
)
async def authenticate(
    request: Request, authentication_service: DAuthenticationService
) -> PrincipalContext:
    auth_headers = request.headers
    return await authentication_service.verify_headers(auth_headers)
