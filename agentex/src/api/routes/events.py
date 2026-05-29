from fastapi import APIRouter, Query

from src.api.schemas.authorization_types import (
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.api.schemas.events import Event
from src.domain.services.authorization_service import DAuthorizationService
from src.domain.use_cases.events_use_case import DEventUseCase
from src.utils.agent_authorization import check_agent_or_collapse_to_404
from src.utils.authorization_shortcuts import DAuthorizedQuery
from src.utils.logging import make_logger

logger = make_logger(__name__)

router = APIRouter(prefix="/events", tags=["Events"])


@router.get(
    "/{event_id}",
    response_model=Event,
)
async def get_event(
    event_id: str,
    event_use_case: DEventUseCase,
    authorization: DAuthorizationService,
) -> Event:
    # Events delegate to their parent agent. Load the event first (404 if it
    # doesn't exist), then check `read` on the parent agent and collapse a
    # denial to 404 — see check_agent_or_collapse_to_404 for the rationale.
    event_entity = await event_use_case.get(event_id)
    await check_agent_or_collapse_to_404(
        authorization, event_entity.agent_id, AuthorizedOperationType.read
    )
    return Event.model_validate(event_entity)


@router.get(
    "",
    response_model=list[Event],
)
async def list_events(
    event_use_case: DEventUseCase,
    task_id: DAuthorizedQuery(
        AgentexResourceType.task,
        AuthorizedOperationType.read,
        "task_id",
        "The task ID to filter events by",
    ),
    agent_id: DAuthorizedQuery(
        AgentexResourceType.agent,
        AuthorizedOperationType.read,
        "agent_id",
        "The agent ID to filter events by",
    ),
    last_processed_event_id: str | None = Query(
        None, description="Optional event ID to get events after this ID"
    ),
    limit: int | None = Query(
        None, description="Optional limit on number of results", ge=1, le=1000
    ),
) -> list[Event]:
    """
    List events for a specific task and agent.

    Optionally filter for events after a specific sequence ID.
    Results are ordered by sequence_id.
    """
    event_entities = await event_use_case.list_events_after_last_processed(
        task_id=task_id,
        agent_id=agent_id,
        last_processed_event_id=last_processed_event_id,
        limit=limit,
    )
    return [Event.model_validate(event_entity) for event_entity in event_entities]
