from fastapi import APIRouter, Query

from src.api.schemas.authorization_types import (
    AgentexResourceType,
    AuthorizedOperationType,
    TaskChildResourceType,
)
from src.api.schemas.events import Event
from src.domain.use_cases.events_use_case import DEventUseCase
from src.utils.authorization_shortcuts import DAuthorizedId, DAuthorizedQuery
from src.utils.logging import make_logger

logger = make_logger(__name__)

router = APIRouter(prefix="/events", tags=["Events"])


@router.get(
    "/{event_id}",
    response_model=Event,
)
async def get_event(
    event_id: DAuthorizedId(TaskChildResourceType.event, AuthorizedOperationType.read),
    event_use_case: DEventUseCase,
) -> Event:
    event_entity = await event_use_case.get(event_id)
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
