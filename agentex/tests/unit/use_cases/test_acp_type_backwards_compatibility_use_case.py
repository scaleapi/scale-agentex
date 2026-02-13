"""
Backwards compatibility tests for ACPType.AGENTIC.
Ensures legacy "agentic" agents continue to work alongside new "async" agents.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.adapters.temporal.adapter_temporal import TemporalAdapter
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.entities.agents_rpc import (
    ACP_TYPE_TO_ALLOWED_RPC_METHODS,
    AgentRPCMethod,
)
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.repositories.event_repository import EventRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.services.agent_acp_service import AgentACPService
from src.domain.services.task_service import AgentTaskService
from src.domain.use_cases.agents_acp_use_case import AgentsACPUseCase
from src.domain.use_cases.agents_use_case import AgentsUseCase


@pytest.mark.unit
class TestACPTypeBackwardsCompatibility:
    """Test that legacy AGENTIC agents work identically to new ASYNC agents"""

    @pytest.mark.asyncio
    async def test_both_agentic_and_async_have_same_allowed_methods(self):
        """Verify AGENTIC and ASYNC have identical RPC method permissions"""
        agentic_methods = set(ACP_TYPE_TO_ALLOWED_RPC_METHODS[ACPType.AGENTIC])
        async_methods = set(ACP_TYPE_TO_ALLOWED_RPC_METHODS[ACPType.ASYNC])

        assert (
            agentic_methods == async_methods
        ), "AGENTIC and ASYNC should have identical allowed RPC methods"

        # Verify they include the expected methods
        expected_methods = {
            AgentRPCMethod.TASK_CREATE,
            AgentRPCMethod.TASK_CANCEL,
            AgentRPCMethod.EVENT_SEND,
        }
        assert agentic_methods == expected_methods
        assert async_methods == expected_methods

    @pytest.mark.asyncio
    async def test_agentic_agent_in_allowed_methods_dictionary(self):
        """Verify AGENTIC is still present in allowed methods dictionary"""
        assert ACPType.AGENTIC in ACP_TYPE_TO_ALLOWED_RPC_METHODS
        assert ACPType.ASYNC in ACP_TYPE_TO_ALLOWED_RPC_METHODS
        assert ACPType.SYNC in ACP_TYPE_TO_ALLOWED_RPC_METHODS

    @pytest.mark.asyncio
    async def test_validate_rpc_method_accepts_agentic_for_task_create(self):
        """Verify AGENTIC agents can use task/create method"""
        # Should not raise an error
        AgentsACPUseCase._validate_rpc_method_for_acp_type(
            ACPType.AGENTIC, AgentRPCMethod.TASK_CREATE
        )

    @pytest.mark.asyncio
    async def test_validate_rpc_method_accepts_agentic_for_event_send(self):
        """Verify AGENTIC agents can use event/send method"""
        # Should not raise an error
        AgentsACPUseCase._validate_rpc_method_for_acp_type(
            ACPType.AGENTIC, AgentRPCMethod.EVENT_SEND
        )

    @pytest.mark.asyncio
    async def test_validate_rpc_method_accepts_agentic_for_task_cancel(self):
        """Verify AGENTIC agents can use task/cancel method"""
        # Should not raise an error
        AgentsACPUseCase._validate_rpc_method_for_acp_type(
            ACPType.AGENTIC, AgentRPCMethod.TASK_CANCEL
        )

    @pytest.mark.asyncio
    async def test_agentic_agent_forwards_task_to_acp(self):
        """Verify AGENTIC agents forward tasks to ACP (not SYNC behavior)"""
        # Setup mocks
        acp_client = AsyncMock(spec=AgentACPService)
        task_repo = AsyncMock(spec=TaskRepository)
        event_repo = AsyncMock(spec=EventRepository)
        stream_repo = AsyncMock()

        task_service = AgentTaskService(
            acp_client=acp_client,
            task_repository=task_repo,
            event_repository=event_repo,
            stream_repository=stream_repo,
        )

        # Create AGENTIC agent
        agentic_agent = AgentEntity(
            id=str(uuid4()),
            name="legacy-agentic-agent",
            description="A legacy agent with agentic type",
            acp_type=ACPType.AGENTIC,
            status=AgentStatus.READY,
            acp_url="http://test-acp.example.com",
        )

        task = TaskEntity(
            id=str(uuid4()),
            name="test-task",
            status=TaskStatus.RUNNING,
        )

        task_repo.create.return_value = task
        acp_client.create_task.return_value = None

        # Execute
        result = await task_service.create_task_and_forward_to_acp(
            agent=agentic_agent,
            task_name="test-task",
            task_params={"test": "params"},
        )

        # Verify task was forwarded to ACP (not skipped like SYNC agents)
        acp_client.create_task.assert_called_once_with(
            agent=agentic_agent,
            task=task,
            acp_url=agentic_agent.acp_url,
            params={"test": "params"},
        )
        assert result == task

    @pytest.mark.asyncio
    async def test_sync_agent_does_not_forward_task_to_acp(self):
        """Verify SYNC agents skip ACP forwarding (baseline for comparison)"""
        # Setup mocks
        acp_client = AsyncMock(spec=AgentACPService)
        task_repo = AsyncMock(spec=TaskRepository)
        event_repo = AsyncMock(spec=EventRepository)
        stream_repo = AsyncMock()

        task_service = AgentTaskService(
            acp_client=acp_client,
            task_repository=task_repo,
            event_repository=event_repo,
            stream_repository=stream_repo,
        )

        # Create SYNC agent
        sync_agent = AgentEntity(
            id=str(uuid4()),
            name="sync-agent",
            description="A sync agent",
            acp_type=ACPType.SYNC,
            status=AgentStatus.READY,
            acp_url="http://test-acp.example.com",
        )

        task = TaskEntity(
            id=str(uuid4()),
            name="test-task",
            status=TaskStatus.RUNNING,
        )

        task_repo.create.return_value = task

        # Execute
        result = await task_service.create_task_and_forward_to_acp(
            agent=sync_agent,
            task_name="test-task",
            task_params={"test": "params"},
        )

        # Verify task was NOT forwarded to ACP (SYNC behavior)
        acp_client.create_task.assert_not_called()
        assert result == task

    @pytest.mark.asyncio
    async def test_async_agent_forwards_task_to_acp(self):
        """Verify ASYNC agents forward tasks to ACP (same as AGENTIC)"""
        # Setup mocks
        acp_client = AsyncMock(spec=AgentACPService)
        task_repo = AsyncMock(spec=TaskRepository)
        event_repo = AsyncMock(spec=EventRepository)
        stream_repo = AsyncMock()

        task_service = AgentTaskService(
            acp_client=acp_client,
            task_repository=task_repo,
            event_repository=event_repo,
            stream_repository=stream_repo,
        )

        # Create ASYNC agent
        async_agent = AgentEntity(
            id=str(uuid4()),
            name="async-agent",
            description="A new async agent",
            acp_type=ACPType.ASYNC,
            status=AgentStatus.READY,
            acp_url="http://test-acp.example.com",
        )

        task = TaskEntity(
            id=str(uuid4()),
            name="test-task",
            status=TaskStatus.RUNNING,
        )

        task_repo.create.return_value = task
        acp_client.create_task.return_value = None

        # Execute
        result = await task_service.create_task_and_forward_to_acp(
            agent=async_agent,
            task_name="test-task",
            task_params={"test": "params"},
        )

        # Verify task was forwarded to ACP (same behavior as AGENTIC)
        acp_client.create_task.assert_called_once_with(
            agent=async_agent,
            task=task,
            acp_url=async_agent.acp_url,
            params={"test": "params"},
        )
        assert result == task

    @pytest.mark.asyncio
    async def test_register_agent_defaults_to_async_not_agentic(self):
        """Verify new agent registrations default to ASYNC, not AGENTIC"""
        # Setup mocks
        agent_repo = AsyncMock(spec=AgentRepository)
        deployment_history_repo = AsyncMock()

        agents_use_case = AgentsUseCase(
            agent_repository=agent_repo,
            deployment_history_repository=deployment_history_repo,
            # Not testing temporal adapter in this test
            temporal_adapter=TemporalAdapter(),
        )

        # Mock repository to return a new agent
        expected_agent = AgentEntity(
            id=str(uuid4()),
            name="new-agent",
            description="A new agent",
            acp_type=ACPType.ASYNC,  # Should be ASYNC by default
            status=AgentStatus.READY,
            acp_url="http://test-acp.example.com",
        )
        agent_repo.get.side_effect = ItemDoesNotExist("Agent not found")
        agent_repo.create.return_value = expected_agent

        # Execute - without specifying acp_type, should default to ASYNC
        await agents_use_case.register_agent(
            name="new-agent",
            description="A new agent",
            acp_url="http://test-acp.example.com",
            # acp_type not specified - should default to ASYNC
        )

        # Verify the call was made with ASYNC
        agent_repo.create.assert_called_once()
        call_args = agent_repo.create.call_args
        created_agent = call_args.kwargs["item"]
        assert created_agent.acp_type == ACPType.ASYNC

    @pytest.mark.asyncio
    async def test_can_explicitly_register_agentic_agent(self):
        """Verify we can still explicitly register AGENTIC agents for backwards compat"""
        # Setup mocks
        agent_repo = AsyncMock(spec=AgentRepository)
        deployment_history_repo = AsyncMock()

        agents_use_case = AgentsUseCase(
            agent_repository=agent_repo,
            deployment_history_repository=deployment_history_repo,
            # Not testing temporal adapter in this test
            temporal_adapter=TemporalAdapter(),
        )

        # Mock repository to return an AGENTIC agent
        expected_agent = AgentEntity(
            id=str(uuid4()),
            name="legacy-agent",
            description="A legacy agent",
            acp_type=ACPType.AGENTIC,
            status=AgentStatus.READY,
            acp_url="http://test-acp.example.com",
        )
        agent_repo.get.side_effect = ItemDoesNotExist("Agent not found")
        agent_repo.create.return_value = expected_agent

        # Execute - explicitly specify AGENTIC
        await agents_use_case.register_agent(
            name="legacy-agent",
            description="A legacy agent",
            acp_url="http://test-acp.example.com",
            acp_type=ACPType.AGENTIC,  # Explicitly set to AGENTIC
        )

        # Verify the call was made with AGENTIC
        agent_repo.create.assert_called_once()
        call_args = agent_repo.create.call_args
        created_agent = call_args.kwargs["item"]
        assert created_agent.acp_type == ACPType.AGENTIC

    @pytest.mark.asyncio
    async def test_agentic_and_async_agents_both_use_not_sync_logic(self):
        """Verify conditional logic treats AGENTIC and ASYNC identically"""
        # Create test agents
        agentic_agent = AgentEntity(
            id=str(uuid4()),
            name="agentic-agent",
            description="Legacy agentic agent",
            acp_type=ACPType.AGENTIC,
            status=AgentStatus.READY,
            acp_url="http://test.com",
        )

        async_agent = AgentEntity(
            id=str(uuid4()),
            name="async-agent",
            description="New async agent",
            acp_type=ACPType.ASYNC,
            status=AgentStatus.READY,
            acp_url="http://test.com",
        )

        sync_agent = AgentEntity(
            id=str(uuid4()),
            name="sync-agent",
            description="Sync agent",
            acp_type=ACPType.SYNC,
            status=AgentStatus.READY,
            acp_url="http://test.com",
        )

        # Test the "!= SYNC" logic that's used in the codebase
        assert agentic_agent.acp_type != ACPType.SYNC, "AGENTIC should not equal SYNC"
        assert async_agent.acp_type != ACPType.SYNC, "ASYNC should not equal SYNC"
        assert sync_agent.acp_type == ACPType.SYNC, "SYNC should equal SYNC"

        # Both AGENTIC and ASYNC should pass the same conditional checks
        agentic_is_not_sync = agentic_agent.acp_type != ACPType.SYNC
        async_is_not_sync = async_agent.acp_type != ACPType.SYNC
        assert (
            agentic_is_not_sync == async_is_not_sync
        ), "AGENTIC and ASYNC should have identical behavior in != SYNC checks"
