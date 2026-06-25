"""Test-only seeding endpoint.

POST /test/seed lets e2e tests insert resource rows directly, bypassing the ACP
runtime. The router is only mounted in app.py when both:
  - env_vars.ENABLE_TEST_SEEDING is true
  - env_vars.ENVIRONMENT is an explicitly-allowed non-prod value
    (Environment.DEV or Environment.STAGING). Unknown / typo'd / unset
    environments fail closed because ENVIRONMENT is typed `str | None`
    with no enum coercion.

Per-request the endpoint also requires the X-Test-Seed-Token header to match
env_vars.TEST_SEED_TOKEN (compared with hmac.compare_digest).

All gate failures return 404 (not 401/403) to avoid advertising the route's
existence on misconfigured deployments. This file + the use case + the env
config + the mount check in app.py are the four removal points if test seeding
ever moves to a separate test-utilities image.
"""

from __future__ import annotations

import hmac
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import Field

from src.api.schemas.events import Event
from src.config.dependencies import GlobalDependencies
from src.config.environment_variables import Environment, EnvironmentVariables
from src.domain.use_cases.test_seeding_use_case import DTestSeedingUseCase
from src.utils.logging import make_logger
from src.utils.model_utils import BaseModel

# Allow-list of non-prod environment names for the seeding gate. Kept in sync
# with the mount-time check in src/api/app.py — any new non-prod environment
# must be added in both places.
_ALLOWED_ENVS: frozenset[str] = frozenset({Environment.DEV, Environment.STAGING})


def get_seeding_env_vars() -> EnvironmentVariables:
    """Named dependency callable for the seeding gate.

    Defined as a named function (not an inline lambda) so tests can override it
    via ``fastapi_app.dependency_overrides[get_seeding_env_vars] = ...``. The
    process-wide ``DEnvironmentVariables`` alias uses an inline lambda which
    cannot be keyed in dependency_overrides.
    """
    return GlobalDependencies().environment_variables

logger = make_logger(__name__)

router = APIRouter(prefix="/test", tags=["TestSeeding"])


# -- request payload schemas ---------------------------------------------------


class _EventSeedPayload(BaseModel):
    """Payload for seeding a single event row."""

    task_id: UUID = Field(..., description="Parent task UUID. Must already exist.")
    agent_id: UUID = Field(..., description="Parent agent UUID. Must already exist.")
    content: dict[str, Any] | None = Field(
        None,
        description=(
            "Optional event content. Will be wrapped in a DataContentEntity and "
            "have audit-marker keys ('seeded', 'seeded_at') added before persist."
        ),
    )
    id: UUID | None = Field(
        None,
        description="Optional event UUID override. Auto-generated if omitted.",
    )


class SeedEventRequest(BaseModel):
    """Discriminated request for seeding an event.

    To add a new seedable resource (task, api_key, schedule, ...), add a sibling
    `SeedXxxRequest` class with `resource_type: Literal["xxx"]`, then add it to
    the `SeedRequest` union below and dispatch in the route handler.
    """

    resource_type: Literal["event"]
    payload: _EventSeedPayload


# When adding a second resource type, change this to:
#   SeedRequest = Annotated[
#       SeedEventRequest | SeedTaskRequest | ...,
#       Field(discriminator="resource_type"),
#   ]
# For now there is a single variant; we keep the discriminated shape so the
# eventual extension is mechanical.
SeedRequest = SeedEventRequest


# -- gate ----------------------------------------------------------------------


def _require_test_seeding_enabled(
    env_vars: Annotated[EnvironmentVariables, Depends(get_seeding_env_vars)],
    x_test_seed_token: Annotated[str | None, Header(alias="X-Test-Seed-Token")] = None,
) -> None:
    """Fail-closed gate for the seeding endpoint.

    All failure modes return 404 (not 401/403) so we don't advertise that the
    route exists on misconfigured deployments. Token comparison is constant-time.
    """
    not_found = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Not Found"
    )

    # Hard env gate, regardless of flag. Allow-list rather than deny-list:
    # ENVIRONMENT is raw os.environ with no enum coercion, so a deny-list
    # against PROD would fail OPEN on unset / "prod" / "Production" / typos /
    # new env names. Fail closed on anything we don't explicitly recognize as
    # non-prod.
    if env_vars.ENVIRONMENT not in _ALLOWED_ENVS:
        raise not_found

    if not env_vars.ENABLE_TEST_SEEDING:
        raise not_found

    expected = env_vars.TEST_SEED_TOKEN
    if not expected:
        # No token configured -> endpoint is unusable even with the flag on.
        raise not_found

    if not x_test_seed_token:
        raise not_found

    if not hmac.compare_digest(x_test_seed_token, expected):
        raise not_found


# -- route ---------------------------------------------------------------------


@router.post(
    "/seed",
    response_model=Event,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_test_seeding_enabled)],
)
async def seed_resource(
    body: SeedRequest,
    request: Request,
    use_case: DTestSeedingUseCase,
) -> Event:
    """Test-only direct insert. Returns the persisted resource entity.

    Extension point: when SeedRequest becomes a true union, dispatch on
    body.resource_type here. Each branch should call into its matching
    `use_case.seed_<resource>(...)` method.
    """
    principal_id: str | None = None
    principal_ctx = getattr(request.state, "principal_context", None)
    if isinstance(principal_ctx, dict):
        principal_id = principal_ctx.get("user_id") or principal_ctx.get(
            "service_account_id"
        )

    if body.resource_type == "event":
        payload = body.payload
        event_entity = await use_case.seed_event(
            task_id=str(payload.task_id),
            agent_id=str(payload.agent_id),
            content=payload.content,
            id_override=str(payload.id) if payload.id is not None else None,
            principal_id=principal_id,
        )
        return Event.model_validate(event_entity)

    # Defensive: the discriminator should make this unreachable.
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported resource_type: {body.resource_type!r}",
    )
