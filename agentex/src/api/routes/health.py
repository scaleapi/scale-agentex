from fastapi import APIRouter, status
from starlette.responses import Response

router = APIRouter(tags=["Health"])


def healthcheck() -> Response:
    """Returns 200 if the app is healthy."""
    return Response(status_code=status.HTTP_200_OK)


health_check_urls = ["healthcheck", "healthz", "readyz"]
for health_check_url in health_check_urls:
    router.get(
        path=f"/{health_check_url}",
        operation_id=health_check_url,
        include_in_schema=False,
    )(healthcheck)
