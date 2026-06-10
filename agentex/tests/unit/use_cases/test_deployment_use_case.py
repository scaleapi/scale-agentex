from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from src.adapters.temporal.adapter_temporal import TemporalAdapter
from src.adapters.temporal.exceptions import TemporalWorkflowNotFoundError
from src.config.environment_variables import EnvironmentVariables
from src.domain.entities.deployments import DeploymentEntity, DeploymentStatus
from src.domain.use_cases.deployment_use_case import DeploymentUseCase
from src.temporal.workflows.healthcheck_workflow import HealthCheckWorkflow
from temporalio.common import WorkflowIDReusePolicy


@pytest.fixture
def enable_health_check_workflow(monkeypatch):
    monkeypatch.setenv("ENABLE_HEALTH_CHECK_WORKFLOW", "true")
    monkeypatch.setenv("AGENTEX_SERVER_TASK_QUEUE", "agentex-server")
    EnvironmentVariables.clear_cache()
    yield
    EnvironmentVariables.clear_cache()


@pytest.fixture
def deployment_repository():
    return AsyncMock()


@pytest.fixture
def agent_repository():
    return AsyncMock()


@pytest.fixture
def temporal_adapter():
    return AsyncMock(spec=TemporalAdapter)


@pytest.fixture
def deployment_use_case(
    deployment_repository,
    agent_repository,
    temporal_adapter,
):
    return DeploymentUseCase(
        deployment_repository=deployment_repository,
        agent_repository=agent_repository,
        temporal_adapter=temporal_adapter,
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_promote_deployment_restarts_healthcheck_with_promoted_acp_url(
    deployment_use_case,
    deployment_repository,
    temporal_adapter,
    enable_health_check_workflow,
):
    agent_id = str(uuid4())
    deployment_id = str(uuid4())
    acp_url = "http://promoted.example.com"
    deployment_repository.promote.return_value = DeploymentEntity(
        id=deployment_id,
        agent_id=agent_id,
        docker_image="example:prod",
        status=DeploymentStatus.READY,
        acp_url=acp_url,
        is_production=True,
    )

    promoted = await deployment_use_case.promote_deployment(
        agent_id=agent_id,
        deployment_id=deployment_id,
    )

    assert promoted.id == deployment_id
    deployment_repository.promote.assert_awaited_once_with(
        agent_id=agent_id,
        deployment_id=deployment_id,
    )
    temporal_adapter.terminate_workflow.assert_awaited_once_with(
        workflow_id=f"healthcheck_workflow_{agent_id}",
        reason=(
            f"Restarting health check workflow for promoted deployment {deployment_id}"
        ),
    )
    temporal_adapter.start_workflow.assert_awaited_once_with(
        workflow_id=f"healthcheck_workflow_{agent_id}",
        workflow=HealthCheckWorkflow,
        args=[{"agent_id": agent_id, "acp_url": acp_url}],
        task_queue="agentex-server",
        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_promote_deployment_starts_healthcheck_when_existing_workflow_missing(
    deployment_use_case,
    deployment_repository,
    temporal_adapter,
    enable_health_check_workflow,
):
    agent_id = str(uuid4())
    deployment_id = str(uuid4())
    acp_url = "http://promoted.example.com"
    deployment_repository.promote.return_value = DeploymentEntity(
        id=deployment_id,
        agent_id=agent_id,
        docker_image="example:prod",
        status=DeploymentStatus.READY,
        acp_url=acp_url,
        is_production=True,
    )
    temporal_adapter.terminate_workflow.side_effect = TemporalWorkflowNotFoundError(
        message="not found"
    )

    await deployment_use_case.promote_deployment(
        agent_id=agent_id,
        deployment_id=deployment_id,
    )

    temporal_adapter.start_workflow.assert_awaited_once_with(
        workflow_id=f"healthcheck_workflow_{agent_id}",
        workflow=HealthCheckWorkflow,
        args=[{"agent_id": agent_id, "acp_url": acp_url}],
        task_queue="agentex-server",
        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_promote_deployment_does_not_start_healthcheck_when_terminate_fails(
    deployment_use_case,
    deployment_repository,
    temporal_adapter,
    enable_health_check_workflow,
):
    agent_id = str(uuid4())
    deployment_id = str(uuid4())
    deployment_repository.promote.return_value = DeploymentEntity(
        id=deployment_id,
        agent_id=agent_id,
        docker_image="example:prod",
        status=DeploymentStatus.READY,
        acp_url="http://promoted.example.com",
        is_production=True,
    )
    temporal_adapter.terminate_workflow.side_effect = RuntimeError("network error")

    await deployment_use_case.promote_deployment(
        agent_id=agent_id,
        deployment_id=deployment_id,
    )

    temporal_adapter.terminate_workflow.assert_awaited_once()
    temporal_adapter.start_workflow.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_promote_deployment_starts_healthcheck_when_existing_workflow_completed(
    deployment_use_case,
    deployment_repository,
    temporal_adapter,
    enable_health_check_workflow,
):
    agent_id = str(uuid4())
    deployment_id = str(uuid4())
    acp_url = "http://promoted.example.com"
    deployment_repository.promote.return_value = DeploymentEntity(
        id=deployment_id,
        agent_id=agent_id,
        docker_image="example:prod",
        status=DeploymentStatus.READY,
        acp_url=acp_url,
        is_production=True,
    )
    temporal_adapter.terminate_workflow.side_effect = RuntimeError(
        "workflow execution already completed"
    )

    await deployment_use_case.promote_deployment(
        agent_id=agent_id,
        deployment_id=deployment_id,
    )

    temporal_adapter.start_workflow.assert_awaited_once_with(
        workflow_id=f"healthcheck_workflow_{agent_id}",
        workflow=HealthCheckWorkflow,
        args=[{"agent_id": agent_id, "acp_url": acp_url}],
        task_queue="agentex-server",
        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
    )
