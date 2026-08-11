from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.domain.entities.agent_api_keys import AgentAPIKeyType
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.repositories.agent_api_key_repository import AgentAPIKeyRepository
from src.domain.repositories.agent_repository import AgentRepository
from src.domain.use_cases.agent_api_keys_use_case import (
    AgentAPIKeysUseCase,
    extract_agent_key_from_authorization,
)
from starlette.datastructures import Headers


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for testing external API calls"""
    mock = AsyncMock()
    return mock


@pytest.fixture
def agent_repository(postgres_session_maker):
    """Real AgentRepository using test PostgreSQL database"""
    return AgentRepository(postgres_session_maker, postgres_session_maker)


@pytest.fixture
def agent_api_key_repository(postgres_session_maker):
    """Real AgentAPIKeyRepository using test PostgreSQL database"""
    return AgentAPIKeyRepository(postgres_session_maker, postgres_session_maker)


@pytest.fixture
def agent_api_keys_use_case(
    agent_api_key_repository, agent_repository, mock_http_client
):
    """Real AgentAPIKeysUseCase instance with real repositories"""
    authorization_service = Mock()
    authorization_service.principal_context = None
    authorization_service.grant = AsyncMock(return_value={})
    authorization_service.revoke = AsyncMock(return_value=None)
    authorization_service.register_resource = AsyncMock(return_value=None)
    authorization_service.deregister_resource = AsyncMock(return_value=None)
    return AgentAPIKeysUseCase(
        agent_api_key_repository=agent_api_key_repository,
        agent_repository=agent_repository,
        client=mock_http_client,
        authorization_service=authorization_service,
    )


@pytest.fixture
def sample_agent():
    """Sample agent entity for testing"""
    return AgentEntity(
        id=str(uuid4()),
        name="test-agent",
        description="A test agent for use case testing",
        acp_type=ACPType.ASYNC,
        status=AgentStatus.READY,
        acp_url="http://test-acp.example.com",
    )


async def create_or_get_agent(agent_repository, agent):
    """Helper to create agent or get existing one"""
    try:
        return await agent_repository.create(agent)
    except Exception:
        # Agent might already exist, sync the ID
        try:
            existing = await agent_repository.get(name=agent.name)
            agent.id = existing.id
            return existing
        except ItemDoesNotExist:
            raise


@pytest.mark.asyncio
@pytest.mark.unit
class TestAgentAPIKeysUseCase:
    """Test suite for AgentAPIKeysUseCase"""

    async def test_create_wrong_agent_id(
        self, agent_api_keys_use_case, agent_repository, sample_agent
    ):
        """Test creating a new API key with a wrong agent ID"""
        with pytest.raises(HTTPException):
            await agent_api_keys_use_case.create(
                name="test-api-key",
                agent_id="non-existent-id",
                api_key_type=AgentAPIKeyType.EXTERNAL,
                api_key="test-api-key-value",
            )

    async def test_delete_by_agent_name(
        self, agent_api_keys_use_case, agent_repository, sample_agent
    ):
        """Test deleting an API key with agent name"""
        await create_or_get_agent(agent_repository, sample_agent)
        result = await agent_api_keys_use_case.create(
            name="test-api-key",
            agent_id=sample_agent.id,
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="test-api-key-value",
        )
        assert result is not None

        await agent_api_keys_use_case.delete_by_agent_name_and_key_name(
            agent_name=sample_agent.name,
            key_name="test-api-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        find_by_name = await agent_api_keys_use_case.get_by_agent_id_and_name(
            agent_id=sample_agent.id,
            name="test-api-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        assert find_by_name is None

        with pytest.raises(ItemDoesNotExist):
            await agent_api_keys_use_case.delete_by_agent_name_and_key_name(
                agent_name=sample_agent.name,
                key_name="test-api-key",
                api_key_type=AgentAPIKeyType.EXTERNAL,
            )

    async def test_delete_by_agent_id(
        self, agent_api_keys_use_case, agent_repository, sample_agent
    ):
        """Test deleting an API key with agent ID"""
        await create_or_get_agent(agent_repository, sample_agent)
        result = await agent_api_keys_use_case.create(
            name="test-api-key",
            agent_id=sample_agent.id,
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="test-api-key-value",
        )
        assert result is not None

        await agent_api_keys_use_case.delete_by_agent_id_and_key_name(
            agent_id=sample_agent.id,
            key_name="test-api-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        find_by_name = await agent_api_keys_use_case.get_by_agent_id_and_name(
            agent_id=sample_agent.id,
            name="test-api-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        assert find_by_name is None

        with pytest.raises(ItemDoesNotExist):
            await agent_api_keys_use_case.delete_by_agent_id_and_key_name(
                agent_id=sample_agent.id,
                key_name="test-api-key",
                api_key_type=AgentAPIKeyType.EXTERNAL,
            )

    async def test_create_external_api_key(
        self, agent_api_keys_use_case, agent_repository, sample_agent
    ):
        """Test creating a new API key"""
        await create_or_get_agent(agent_repository, sample_agent)
        result = await agent_api_keys_use_case.create(
            name="test-api-key",
            agent_id=sample_agent.id,
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="test-api-key-value",
        )
        assert result.name == "test-api-key"
        assert result.agent_id == sample_agent.id
        assert result.api_key_type == AgentAPIKeyType.EXTERNAL
        assert result.api_key is not None

        find_by_name = await agent_api_keys_use_case.get_by_agent_id_and_name(
            agent_id=sample_agent.id,
            name="test-api-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        assert find_by_name is not None
        assert find_by_name.name == "test-api-key"

        find_by_wrong_name = await agent_api_keys_use_case.get_by_agent_id_and_name(
            agent_id=sample_agent.id,
            name="non-existent-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        assert find_by_wrong_name is None

        find_by_wrong_id = await agent_api_keys_use_case.get_by_agent_id_and_name(
            agent_id="non-existent-id",
            name="non-existent-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        assert find_by_wrong_id is None

        find_by_key = await agent_api_keys_use_case.get_external_by_agent_id_and_key(
            agent_id=sample_agent.id, api_key=result.api_key
        )
        assert find_by_key is not None
        assert find_by_key.api_key == result.api_key
        assert find_by_key.name == "test-api-key"

        find_by_wrong_key = (
            await agent_api_keys_use_case.get_external_by_agent_id_and_key(
                agent_id=sample_agent.id, api_key="non-existent-key"
            )
        )
        assert find_by_wrong_key is None

        await agent_api_keys_use_case.delete_by_agent_id_and_key_name(
            agent_id=sample_agent.id,
            key_name="test-api-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        find_after_delete = await agent_api_keys_use_case.get_by_agent_id_and_name(
            agent_id=sample_agent.id,
            name="test-api-key",
            api_key_type=AgentAPIKeyType.EXTERNAL,
        )
        assert find_after_delete is None


class _FakeRequest:
    """Minimal Request stand-in exposing the header dict the use case reads.

    Uses Starlette's ``Headers`` so lookups are case-insensitive, matching
    real HTTP request semantics for cases like ``Authorization`` vs
    ``authorization``.
    """

    def __init__(self, headers: dict[str, str]):
        self.headers = Headers(headers)


@pytest.mark.unit
class TestExtractAgentKeyFromAuthorization:
    """Pure-function tests for the Authorization header parser."""

    def test_returns_none_for_absent_header(self):
        assert extract_agent_key_from_authorization(None) is None
        assert extract_agent_key_from_authorization("") is None

    def test_extracts_agent_key(self):
        assert extract_agent_key_from_authorization("AgentKey abc123") == "abc123"

    def test_scheme_is_case_insensitive(self):
        # RFC 9110 § 11.6.1 requires case-insensitive scheme matching.
        assert extract_agent_key_from_authorization("agentkey abc123") == "abc123"
        assert extract_agent_key_from_authorization("AGENTKEY abc123") == "abc123"
        assert extract_agent_key_from_authorization("aGeNtKeY abc123") == "abc123"

    def test_ignores_bearer_scheme(self):
        # Preserves existing ``Authorization: Bearer ...`` semantics for SGP.
        assert extract_agent_key_from_authorization("Bearer sgp-token") is None

    def test_ignores_basic_scheme(self):
        assert extract_agent_key_from_authorization("Basic dXNlcjpwYXNz") is None

    def test_returns_none_for_empty_credentials(self):
        assert extract_agent_key_from_authorization("AgentKey") is None
        assert extract_agent_key_from_authorization("AgentKey ") is None
        assert extract_agent_key_from_authorization("AgentKey   ") is None

    def test_strips_surrounding_whitespace(self):
        assert (
            extract_agent_key_from_authorization("  AgentKey  abc123  ") == "abc123"
        )


@pytest.mark.asyncio
@pytest.mark.unit
class TestValidateAgentIdentityHeadersAuthorizationScheme:
    """End-to-end coverage of the AgentKey Authorization scheme.

    Each case exercises ``validate_agent_identity_headers`` so both the
    header parsing and the shared DB verification path are covered.
    """

    async def test_authorization_agent_key_valid(
        self, agent_api_keys_use_case, agent_repository, sample_agent
    ):
        await create_or_get_agent(agent_repository, sample_agent)
        created = await agent_api_keys_use_case.create(
            name="webhook-key",
            agent_id=sample_agent.id,
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="ironclad-secret",
        )
        request = _FakeRequest({"Authorization": f"AgentKey {created.api_key}"})
        result = await agent_api_keys_use_case.validate_agent_identity_headers(
            sample_agent.id, request, b""
        )
        assert result is None

    async def test_authorization_agent_key_invalid_returns_401(
        self, agent_api_keys_use_case, agent_repository, sample_agent
    ):
        await create_or_get_agent(agent_repository, sample_agent)
        request = _FakeRequest({"Authorization": "AgentKey bogus-key"})
        result = await agent_api_keys_use_case.validate_agent_identity_headers(
            sample_agent.id, request, b""
        )
        assert result is not None
        assert result.status_code == 401

    async def test_authorization_agent_key_revoked_returns_401(
        self, agent_api_keys_use_case, agent_repository, sample_agent
    ):
        # Revocation = the key row no longer exists; must produce identical
        # semantics to ``x-agent-api-key`` (401).
        await create_or_get_agent(agent_repository, sample_agent)
        created = await agent_api_keys_use_case.create(
            name="webhook-key",
            agent_id=sample_agent.id,
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="revoked-secret",
        )
        await agent_api_keys_use_case.delete(id=created.id)
        request = _FakeRequest({"Authorization": f"AgentKey {created.api_key}"})
        result = await agent_api_keys_use_case.validate_agent_identity_headers(
            sample_agent.id, request, b""
        )
        assert result is not None
        assert result.status_code == 401

    async def test_authorization_agent_key_wrong_agent_returns_401(
        self, agent_api_keys_use_case, agent_repository, sample_agent
    ):
        # A key registered under one agent must not authenticate a forward
        # request addressed to a different agent.
        await create_or_get_agent(agent_repository, sample_agent)
        created = await agent_api_keys_use_case.create(
            name="webhook-key",
            agent_id=sample_agent.id,
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="scoped-secret",
        )
        request = _FakeRequest({"Authorization": f"AgentKey {created.api_key}"})
        result = await agent_api_keys_use_case.validate_agent_identity_headers(
            "some-other-agent-id", request, b""
        )
        assert result is not None
        assert result.status_code == 401

    async def test_authorization_bearer_token_does_not_match_agent_key_path(
        self, agent_api_keys_use_case, agent_repository, sample_agent
    ):
        # Regression: an ``Authorization: Bearer ...`` request must NOT be
        # consumed by the AgentKey path. With the auth gateway disabled in the
        # test harness the fallthrough surfaces as the "missing authentication"
        # 403 rather than a 401 from the AgentKey invalid-key branch.
        await create_or_get_agent(agent_repository, sample_agent)
        request = _FakeRequest({"Authorization": "Bearer sgp-token"})
        result = await agent_api_keys_use_case.validate_agent_identity_headers(
            sample_agent.id, request, b""
        )
        assert result is not None
        assert result.status_code == 403

    async def test_x_agent_api_key_header_still_authenticates(
        self, agent_api_keys_use_case, agent_repository, sample_agent
    ):
        # Regression: the pre-existing ``X-Agent-API-Key`` path is unchanged.
        await create_or_get_agent(agent_repository, sample_agent)
        created = await agent_api_keys_use_case.create(
            name="legacy-key",
            agent_id=sample_agent.id,
            api_key_type=AgentAPIKeyType.EXTERNAL,
            api_key="legacy-secret",
        )
        request = _FakeRequest({"X-Agent-API-Key": created.api_key})
        result = await agent_api_keys_use_case.validate_agent_identity_headers(
            sample_agent.id, request, b""
        )
        assert result is None
