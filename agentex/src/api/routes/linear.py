"""Linear gateway ingress — POST /linear/events.

The webhook URL for the ``@agentex`` Linear agent app. Auth-whitelisted (like
/slack) because Linear can't present an SGP principal; the Linear-Signature is the
auth, verified in the use case against the app's webhook signing secret. Delegates
all logic to LinearGatewayUseCase.
"""

from fastapi import APIRouter, BackgroundTasks, Request

from src.domain.use_cases.linear_gateway_use_case import DLinearGatewayUseCase

router = APIRouter(prefix="/linear", tags=["Linear"])


@router.post("/events", summary="Linear agent webhook ingress for the @agentex app")
async def linear_events(
    request: Request,
    background: BackgroundTasks,
    use_case: DLinearGatewayUseCase,
) -> dict:
    # Read the raw body first (needed for HMAC signature verification), then parse.
    body = await request.body()
    payload = await request.json()
    headers = {k.lower(): v for k, v in request.headers.items()}
    return await use_case.handle_linear_event(
        body=body, headers=headers, payload=payload, background=background
    )
