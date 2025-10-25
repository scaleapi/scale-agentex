from fastapi import APIRouter, HTTPException, Query

from src.api.schemas.agent_task_tracker import (
    AgentTaskTracker,
    UpdateAgentTaskTrackerRequest,
)
from src.domain.exceptions import ClientError
from src.domain.use_cases.agent_task_tracker_use_case import (
    DAgentTaskTrackerUseCase,
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
    tracker_id: str,
    agent_task_tracker_use_case: DAgentTaskTrackerUseCase,
) -> AgentTaskTracker:
    """
    Get agent task tracker for a specific agent and task.
    """
    try:
        state = await agent_task_tracker_use_case.get_agent_task_tracker(
            tracker_id=tracker_id
        )
        return AgentTaskTracker.model_validate(state)
    except ClientError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error getting processing state: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "",
    response_model=list[AgentTaskTracker],
    summary="List Agent Task Trackers",
    description="List all agent task trackers, optionally filtered by query parameters.",
)
async def filter_agent_task_tracker(
    agent_task_tracker_use_case: DAgentTaskTrackerUseCase,
    agent_id: str | None = Query(None, description="Agent ID"),
    task_id: str | None = Query(None, description="Task ID"),
    limit: int = Query(50, description="Limit", ge=1),
    page_number: int = Query(1, description="Page number", ge=1),
) -> list[AgentTaskTracker]:
    """
    Filter agent task tracker by query parameters.
    """
    agent_task_tracker_entities = await agent_task_tracker_use_case.list(
        agent_id=agent_id, task_id=task_id, limit=limit, page_number=page_number
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
    tracker_id: str,
    request: UpdateAgentTaskTrackerRequest,
    agent_task_tracker_use_case: DAgentTaskTrackerUseCase,
) -> AgentTaskTracker:
    """
    Update agent task tracker
    """
    try:
        state = await agent_task_tracker_use_case.update_agent_task_tracker(
            tracker_id=tracker_id,
            last_processed_event_id=request.last_processed_event_id,
            status=request.status,
            status_reason=request.status_reason,
        )
        return AgentTaskTracker.model_validate(state)
    except ClientError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error committing cursor: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
