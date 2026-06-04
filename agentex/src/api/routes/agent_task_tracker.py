from fastapi import APIRouter, HTTPException, Query

from src.api.schemas.agent_task_tracker import (
    AgentTaskTracker,
    UpdateAgentTaskTrackerRequest,
)
from src.api.schemas.authorization_types import (
    AgentexResourceType,
    AuthorizedOperationType,
    TaskChildResourceType,
)
from src.domain.exceptions import ClientError
from src.domain.use_cases.agent_task_tracker_use_case import (
    DAgentTaskTrackerUseCase,
)
from src.utils.authorization_shortcuts import (
    DAuthorizedId,
    DAuthorizedResourceIds,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)

router = APIRouter(prefix="/tracker", tags=["Agent Task Tracker"])


@router.get(
    "/{tracker_id}",
    response_model=AgentTaskTracker,
    summary="Get Agent Task Tracker",
    description="Get agent task tracker by tracker ID",
)
async def get_agent_task_tracker(
    tracker_id: DAuthorizedId(
        TaskChildResourceType.agent_task_tracker,
        AuthorizedOperationType.read,
        param_name="tracker_id",
    ),
    agent_task_tracker_use_case: DAgentTaskTrackerUseCase,
) -> AgentTaskTracker:
    try:
        tracker = await agent_task_tracker_use_case.get_agent_task_tracker(
            tracker_id=tracker_id
        )
        return AgentTaskTracker.model_validate(tracker)
    except ClientError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error getting agent task tracker: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "",
    response_model=list[AgentTaskTracker],
    summary="List Agent Task Trackers",
    description="List all agent task trackers, optionally filtered by query parameters.",
)
async def filter_agent_task_tracker(
    agent_task_tracker_use_case: DAgentTaskTrackerUseCase,
    authorized_task_ids: DAuthorizedResourceIds(AgentexResourceType.task),
    agent_id: str | None = Query(None, description="Agent ID"),
    task_id: str | None = Query(None, description="Task ID"),
    limit: int = Query(50, description="Limit", ge=1),
    page_number: int = Query(1, description="Page number", ge=1),
    order_by: str | None = Query(None, description="Field to order by"),
    order_direction: str = Query("desc", description="Order direction (asc or desc)"),
) -> list[AgentTaskTracker]:
    if authorized_task_ids is None:
        # Authz bypassed: honor the explicit task_id filter if given, else no
        # task restriction.
        effective_task_ids = [task_id] if task_id else None
    elif task_id is not None:
        # Explicit task_id is only honored if the caller is authorized for it;
        # otherwise the result set is empty (IN ()).
        effective_task_ids = [task_id] if task_id in authorized_task_ids else []
    else:
        effective_task_ids = authorized_task_ids

    agent_task_tracker_entities = await agent_task_tracker_use_case.list(
        agent_id=agent_id,
        task_ids=effective_task_ids,
        limit=limit,
        page_number=page_number,
        order_by=order_by,
        order_direction=order_direction,
    )
    return [
        AgentTaskTracker.model_validate(entity)
        for entity in agent_task_tracker_entities
    ]


@router.put(
    "/{tracker_id}",
    response_model=AgentTaskTracker,
    summary="Update Agent Task Tracker",
    description="Update agent task tracker by tracker ID",
)
async def update_agent_task_tracker(
    tracker_id: DAuthorizedId(
        TaskChildResourceType.agent_task_tracker,
        AuthorizedOperationType.execute,
        param_name="tracker_id",
    ),
    request: UpdateAgentTaskTrackerRequest,
    agent_task_tracker_use_case: DAgentTaskTrackerUseCase,
) -> AgentTaskTracker:
    try:
        tracker = await agent_task_tracker_use_case.update_agent_task_tracker(
            tracker_id=tracker_id,
            last_processed_event_id=request.last_processed_event_id,
            status=request.status,
            status_reason=request.status_reason,
        )
        return AgentTaskTracker.model_validate(tracker)
    except ClientError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error updating agent task tracker: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
