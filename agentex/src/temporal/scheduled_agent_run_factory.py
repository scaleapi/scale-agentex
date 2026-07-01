"""
Wire the dependencies the scheduled-agent-run activity needs outside FastAPI's
Depends DI, for use inside the Temporal worker. Mirrors the manual-wiring pattern
in task_retention_factory.py.

Each scheduled fire creates a fresh Agentex task and delivers the schedule's
configured initial input under the *stored creator principal* —
not as an agent identity. So the AgentsACPUseCase is rebuilt per fire with an
AuthorizationService whose principal_context is that fire's creator principal and
whose agent_identity is None, attributing task ownership and AuthZ checks to the
schedule's creator rather than to the worker's service identity.
"""

from types import SimpleNamespace
from typing import Any

from src.adapters.authorization.adapter_agentex_authz_proxy import (
    AgentexAuthorizationProxy,
)
from src.adapters.http.adapter_httpx import HttpxGateway
from src.adapters.streams.adapter_redis import RedisStreamRepository
from src.api.middleware_utils import resolve_authorization_enabled
from src.config.dependencies import (
    GlobalDependencies,
    database_async_read_only_session_maker,
    database_async_read_write_engine,
    database_async_read_write_session_maker,
    resolve_environment_variable_dependency,
)
from src.config.environment_variables import EnvironmentVariables, EnvVarKeys
from src.domain.repositories.agent_api_key_repository import AgentAPIKeyRepository
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.repositories.agent_run_schedule_repository import (
    AgentRunScheduleRepository,
)
from src.domain.repositories.deployment_repository import DeploymentRepository
from src.domain.repositories.event_repository import EventRepository
from src.domain.repositories.task_message_repository import TaskMessageRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.repositories.task_state_repository import TaskStateRepository
from src.domain.services.agent_acp_service import AgentACPService
from src.domain.services.authorization_service import AuthorizationService
from src.domain.services.task_message_service import TaskMessageService
from src.domain.services.task_service import AgentTaskService
from src.domain.use_cases.agents_acp_use_case import AgentsACPUseCase


class _ScheduledRunRequest:
    """Minimal ``Request`` stand-in for worker-side AuthZ + ACP delegation.

    Carries the stored creator principal as ``state.principal_context`` with no
    ``agent_identity`` (so AuthZ attributes ownership to the creator, not a
    service) and no headers (so no live user credentials — cookies, API keys —
    are forwarded downstream). ``build_delegation_headers`` returns an
    empty mapping when there are no inbound credential headers, which is exactly
    the intended behavior here.
    """

    def __init__(self, principal_context: dict[str, Any] | None):
        self.state = SimpleNamespace(
            principal_context=principal_context,
            agent_identity=None,
        )
        self.headers: dict[str, str] = {}


def build_agent_run_schedule_repository(
    global_dependencies: GlobalDependencies,
) -> AgentRunScheduleRepository:
    """Build the schedule repository from an already-loaded GlobalDependencies."""
    engine = database_async_read_write_engine()
    rw_session_maker = database_async_read_write_session_maker(engine)
    ro_session_maker = database_async_read_only_session_maker(engine)
    return AgentRunScheduleRepository(rw_session_maker, ro_session_maker)


def build_acp_use_case_for_principal(
    global_dependencies: GlobalDependencies,
    creator_principal: dict[str, Any] | None,
) -> AgentsACPUseCase:
    """Construct an AgentsACPUseCase bound to a specific creator principal.

    The returned use case routes task creation and initial-input delivery exactly
    as the JSON-RPC path does (ACP-type validation, acp_url resolution, ownership
    grant, get-or-create idempotency), but attributes everything to
    *creator_principal* instead of the request principal.
    """
    env = EnvironmentVariables.refresh()
    engine = database_async_read_write_engine()
    rw_session_maker = database_async_read_write_session_maker(engine)
    ro_session_maker = database_async_read_only_session_maker(engine)

    request = _ScheduledRunRequest(creator_principal)

    agent_repository = AgentRepository(rw_session_maker, ro_session_maker)
    agent_api_key_repository = AgentAPIKeyRepository(rw_session_maker, ro_session_maker)
    deployment_repository = DeploymentRepository(rw_session_maker, ro_session_maker)
    task_repository = TaskRepository(rw_session_maker, ro_session_maker)
    event_repository = EventRepository(rw_session_maker, ro_session_maker)

    task_state_repository = TaskStateRepository(global_dependencies.mongodb_database)
    task_message_repository = TaskMessageRepository(
        global_dependencies.mongodb_database
    )
    task_message_service = TaskMessageService(
        message_repository=task_message_repository
    )

    http_gateway = HttpxGateway(env)
    stream_repository = RedisStreamRepository(env, global_dependencies.redis_pool)

    auth_url = resolve_environment_variable_dependency(EnvVarKeys.AGENTEX_AUTH_URL)
    authz_gateway = AgentexAuthorizationProxy(agentex_auth_url=auth_url)
    authorization_service = AuthorizationService(
        enabled=resolve_authorization_enabled(auth_url),
        gateway=authz_gateway,
        request=request,  # type: ignore[arg-type]
    )

    acp_client = AgentACPService(
        agent_repository=agent_repository,
        agent_api_key_repository=agent_api_key_repository,
        http_gateway=http_gateway,
        request=request,  # type: ignore[arg-type]
    )
    task_service = AgentTaskService(
        acp_client=acp_client,
        task_state_repository=task_state_repository,
        task_repository=task_repository,
        event_repository=event_repository,
        stream_repository=stream_repository,
        authorization_service=authorization_service,
    )
    return AgentsACPUseCase(
        agent_repository=agent_repository,
        deployment_repository=deployment_repository,
        acp_client=acp_client,
        task_service=task_service,
        task_message_service=task_message_service,
        authorization_service=authorization_service,
    )
