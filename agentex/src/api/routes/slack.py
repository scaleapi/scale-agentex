"""Slack gateway ingress — POST /slack/events and /slack/commands.

The Request URLs for the ``@agent`` Slack app. Auth-whitelisted (like
/agents/forward) because Slack can't present an SGP principal; the Slack signature
is the auth, verified in the use case against the app's signing secret from the
secrets microservice. Delegates all logic to SlackGatewayUseCase.
"""

from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse

from src.domain.use_cases.slack_gateway_use_case import DSlackGatewayUseCase

router = APIRouter(prefix="/slack", tags=["Slack"])


def _slack_ack(payload: dict) -> Response:
    """Turn a use-case result into what Slack actually expects on the wire.

    Slack renders a slash-command / interaction response body verbatim, and "show
    nothing" has to be a genuinely EMPTY 200 — an empty dict is still a body, which
    FastAPI serializes to `{}`, and Slack prints that literally in the channel
    (`/agents` opened its modal and left a stray `{}` behind). A non-empty payload
    is a real message and is passed through as JSON.
    """
    if not payload:
        return Response(status_code=200)
    return JSONResponse(payload)


@router.post("/events", summary="Slack Events API ingress for the @agent app")
async def slack_events(
    request: Request,
    background: BackgroundTasks,
    use_case: DSlackGatewayUseCase,
) -> dict:
    body = await request.body()
    payload = await request.json()
    headers = {k.lower(): v for k, v in request.headers.items()}
    return await use_case.handle_slack_event(
        body=body, headers=headers, payload=payload, background=background
    )


@router.post("/commands", summary="Slack slash-command ingress (e.g. /agents)")
async def slack_commands(
    request: Request,
    use_case: DSlackGatewayUseCase,
) -> Response:
    # Slash commands are application/x-www-form-urlencoded, not JSON. Read the raw
    # body first (needed for signature verification), then parse the form.
    body = await request.body()
    form = dict(await request.form())
    headers = {k.lower(): v for k, v in request.headers.items()}
    return _slack_ack(
        await use_case.handle_slash_command(body=body, headers=headers, form=form)
    )


@router.post("/interactions", summary="Slack interactivity ingress (modals, shortcuts)")
async def slack_interactions(
    request: Request,
    background: BackgroundTasks,
    use_case: DSlackGatewayUseCase,
) -> Response:
    # Interactions are form-encoded with a JSON `payload` field. Raw body first (for
    # signature verification), then the form. The turn runs out-of-band like events.
    body = await request.body()
    form = dict(await request.form())
    headers = {k.lower(): v for k, v in request.headers.items()}
    return _slack_ack(
        await use_case.handle_interaction(
            body=body, headers=headers, form=form, background=background
        )
    )
