"""
Construct a TaskRetentionUseCase outside FastAPI's Depends DI, for use inside
Temporal worker processes. Mirrors the manual-wiring pattern in
run_healthcheck_workflow.py (repositories built from session makers).
"""

from src.adapters.temporal.adapter_temporal import TemporalAdapter
from src.config.dependencies import (
    GlobalDependencies,
    database_async_read_only_session_maker,
    database_async_read_write_engine,
    database_async_read_write_session_maker,
    httpx_client,
)
from src.domain.repositories.agent_task_tracker_repository import (
    AgentTaskTrackerRepository,
)
from src.domain.repositories.event_repository import EventRepository
from src.domain.repositories.task_message_repository import TaskMessageRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.repositories.task_state_repository import TaskStateRepository
from src.domain.services.task_message_service import TaskMessageService
from src.domain.services.task_retention_service import TaskRetentionService
from src.domain.use_cases.task_retention_use_case import TaskRetentionUseCase


def build_task_retention_use_case(
    global_dependencies: GlobalDependencies,
) -> TaskRetentionUseCase:
    """Wire a TaskRetentionUseCase from an already-loaded GlobalDependencies."""
    engine = database_async_read_write_engine()
    rw_session_maker = database_async_read_write_session_maker(engine)
    ro_session_maker = database_async_read_only_session_maker(engine)

    task_repository = TaskRepository(rw_session_maker, ro_session_maker)
    event_repository = EventRepository(rw_session_maker, ro_session_maker)
    agent_task_tracker_repository = AgentTaskTrackerRepository(
        rw_session_maker, ro_session_maker
    )

    task_message_repository = TaskMessageRepository(
        global_dependencies.mongodb_database
    )
    task_state_repository = TaskStateRepository(global_dependencies.mongodb_database)
    task_message_service = TaskMessageService(
        message_repository=task_message_repository
    )

    temporal_adapter = TemporalAdapter(
        temporal_client=global_dependencies.temporal_client
    )

    retention_service = TaskRetentionService(
        task_repository=task_repository,
        task_message_service=task_message_service,
        task_message_repository=task_message_repository,
        task_state_repository=task_state_repository,
        event_repository=event_repository,
        agent_task_tracker_repository=agent_task_tracker_repository,
        temporal_adapter=temporal_adapter,
        httpx_client=httpx_client(),
    )
    return TaskRetentionUseCase(retention_service=retention_service)
