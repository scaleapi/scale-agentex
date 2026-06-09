import hashlib
import hmac
import json
import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from starlette.background import BackgroundTask

from src.adapters.authentication.adapter_agentex_authn_proxy import (
    AgentexAuthenticationProxy,
)
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.middleware_utils import get_request_headers_to_forward, verify_auth_gateway
from src.api.schemas.authorization_types import AgentexResource
from src.config.dependencies import (
    DHttpxClient,
    resolve_environment_variable_dependency,
)
from src.config.environment_variables import EnvVarKeys
from src.domain.entities.agent_api_keys import (
    AgentAPIKeyEntity,
    AgentAPIKeyType,
)
from src.domain.entities.agents import AgentEntity, AgentStatus
from src.domain.repositories.agent_api_key_repository import (
    DAgentAPIKeyRepository,
)
from src.domain.repositories.agent_repository import DAgentRepository
from src.domain.services.authorization_service import DAuthorizationService
from src.utils.ids import orm_id
from src.utils.logging import make_logger

logger = make_logger(__name__)


class AgentAPIKeysUseCase:
    def __init__(
        self,
        agent_api_key_repository: DAgentAPIKeyRepository,
        agent_repository: DAgentRepository,
        client: DHttpxClient,
        authorization_service: DAuthorizationService,
    ):
        self.agent_api_key_repo = agent_api_key_repository
        self.agent_repo = agent_repository
        self.client = client
        self.authorization_service = authorization_service
        self.auth_gateway_enabled = bool(
            resolve_environment_variable_dependency(EnvVarKeys.AGENTEX_AUTH_URL)
        )
        self.auth_gateway = AgentexAuthenticationProxy(
            agentex_auth_url=resolve_environment_variable_dependency(
                EnvVarKeys.AGENTEX_AUTH_URL
            ),
            environment=resolve_environment_variable_dependency(EnvVarKeys.ENVIRONMENT),
        )
        self.webhook_request_timeout = resolve_environment_variable_dependency(
            EnvVarKeys.WEBHOOK_REQUEST_TIMEOUT
        )

    async def get_agent(
        self, agent_id: str | None = None, agent_name: str | None = None
    ) -> AgentEntity | None:
        try:
            agent = await self.agent_repo.get(id=agent_id, name=agent_name)
            if agent.status == AgentStatus.DELETED:
                return None
            return agent
        except ItemDoesNotExist:
            logger.error(
                f"Agent with ID {agent_id} and name {agent_name} does not exist."
            )
            return None

    async def create(
        self,
        name: str,
        agent_id: str,
        api_key_type: AgentAPIKeyType,
        api_key: str,
    ) -> AgentAPIKeyEntity:
        agent = await self.get_agent(agent_id=agent_id)
        if not agent:
            raise HTTPException(
                status_code=404,
                detail=f"Agent ID {agent_id} not found.",
            )

        api_key_id = orm_id()

        await self._register_api_key_in_auth(
            api_key_id=api_key_id,
            agent_id=agent.id,
        )

        # TODO: encrypt API key before storing it
        # Initialize a new agent api_key
        agent_api_key = AgentAPIKeyEntity(
            id=api_key_id,
            name=name,
            agent_id=agent.id,
            api_key_type=api_key_type,
            api_key=api_key,
        )
        return await self.agent_api_key_repo.create(item=agent_api_key)

    async def _register_api_key_in_auth(
        self,
        *,
        api_key_id: str,
        agent_id: str,
    ) -> None:
        """Register a new agent_api_key in the authorization graph before persist.

        The api key is registered under its parent agent so permissions cascade
        from the owning agent. Registering before the Postgres row is created
        fails closed: a failure aborts the create rather than leaving a
        persisted api key that cannot be authorized.
        """
        principal_context = self.authorization_service.principal_context
        # principal_context is `Any` (a dict from /v1/authn), not a typed model,
        # so getattr always yields None and silently skips the Spark register.
        if isinstance(principal_context, dict):
            user_id = principal_context.get("user_id")
            service_account_id = principal_context.get("service_account_id")
        else:
            user_id = getattr(principal_context, "user_id", None)
            service_account_id = getattr(principal_context, "service_account_id", None)
        if user_id is None and service_account_id is None:
            logger.warning(
                "Skipping auth registration for api_key: no creator resolvable",
                extra={
                    "api_key_id": api_key_id,
                    "agent_id": agent_id,
                },
            )
            return
        try:
            await self.authorization_service.register_resource(
                resource=AgentexResource.api_key(api_key_id),
                parent=AgentexResource.agent(agent_id),
            )
        except Exception as exc:
            logger.exception(
                "Auth registration failed for agent_api_key; aborting create",
                extra={
                    "api_key_id": api_key_id,
                    "agent_id": agent_id,
                    "error_type": type(exc).__name__,
                },
            )
            raise

    async def _deregister_api_key_from_auth(self, *, api_key_id: str) -> None:
        """Best-effort removal of the api_key from the authorization graph.

        Deletes treat Postgres as the source of truth for existence. Once the
        row is gone, a deregister failure is logged but does not block the
        delete response.
        """
        try:
            await self.authorization_service.deregister_resource(
                resource=AgentexResource.api_key(api_key_id),
            )
        except Exception as exc:
            logger.warning(
                "Auth deregister failed for agent_api_key; entry may be orphaned",
                extra={
                    "api_key_id": api_key_id,
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )

    async def get(self, id: str) -> AgentAPIKeyEntity:
        return await self.agent_api_key_repo.get(id=id)

    async def get_internal_api_key_by_agent_id(
        self, agent_id: str
    ) -> AgentAPIKeyEntity | None:
        """
        Get the internal API key for an agent by its ID.
        This is used for internal communication between agents.
        """
        return await self.agent_api_key_repo.get_internal_api_key_by_agent_id(
            agent_id=agent_id
        )

    async def get_by_agent_id_and_name(
        self, agent_id: str, name: str, api_key_type: AgentAPIKeyType
    ) -> AgentAPIKeyEntity | None:
        return await self.agent_api_key_repo.get_by_agent_id_and_name(
            agent_id=agent_id, name=name, api_key_type=api_key_type
        )

    async def get_external_by_agent_id_and_key(
        self, agent_id: str, api_key: str
    ) -> AgentAPIKeyEntity | None:
        # TODO: query by encrypted API key
        return await self.agent_api_key_repo.get_external_by_agent_id_and_key(
            agent_id=agent_id, api_key=api_key
        )

    async def delete(self, id: str) -> None:
        # Pre-fetch so we skip both the delete and auth cleanup when the row
        # never existed: no DB round-trip, no auth round-trip for a no-op.
        try:
            await self.agent_api_key_repo.get(id=id)
        except ItemDoesNotExist:
            return
        await self.agent_api_key_repo.delete(id=id)
        await self._deregister_api_key_from_auth(api_key_id=id)

    async def delete_by_agent_id_and_key_name(
        self,
        agent_id: str,
        key_name: str,
        api_key_type: AgentAPIKeyType,
    ) -> None:
        existing = await self.agent_api_key_repo.get_by_agent_id_and_name(
            agent_id=agent_id, name=key_name, api_key_type=api_key_type
        )
        await self.agent_api_key_repo.delete_by_agent_id_and_key_name(
            agent_id=agent_id, key_name=key_name, api_key_type=api_key_type
        )
        if existing is not None:
            await self._deregister_api_key_from_auth(api_key_id=existing.id)

    async def delete_by_agent_name_and_key_name(
        self,
        agent_name: str,
        key_name: str,
        api_key_type: AgentAPIKeyType,
    ) -> None:
        existing = await self.agent_api_key_repo.get_by_agent_name_and_key_name(
            agent_name, key_name, api_key_type
        )
        await self.agent_api_key_repo.delete_by_agent_name_and_key_name(
            agent_name=agent_name, key_name=key_name, api_key_type=api_key_type
        )
        if existing is not None:
            await self._deregister_api_key_from_auth(api_key_id=existing.id)

    async def list(
        self,
        agent_id: str,
        limit: int,
        page_number: int,
        id: list[str] | None = None,
    ) -> list[AgentAPIKeyEntity]:
        # ``id`` is the authorization-filter shape used by route deps (DAuthorizedResourceIds).
        # ``None`` means "no filter" (e.g. authz bypass); an empty list means
        # "caller can see no api_keys" and must short-circuit to avoid the
        # base repo translating ``id=[]`` into an unfiltered query.
        if id is not None and not id:
            return []
        filters: dict = {"agent_id": agent_id}
        if id is not None:
            filters["id"] = id
        return await self.agent_api_key_repo.list(
            limit=limit, page_number=page_number, filters=filters
        )

    async def forward_agent_request(
        self,
        agent_name: str,
        path: str,
        request: Request,
    ):
        """Forward a request to an agent by its unique ID."""
        agent = await self.get_agent(agent_name=agent_name)
        if not agent or not agent.acp_url:
            return JSONResponse(
                status_code=404,
                content={"detail": f"Agent {agent_name} not found or has no ACP URL."},
            )
        agent_id = agent.id

        content = await request.body()
        # Slack verification has a challenge in the body that needs to be returned.
        if request.headers.get("X-Slack-Request-Timestamp"):
            # Slack verification request, return the challenge
            try:
                body_json = json.loads(content.decode("utf-8"))
                challenge = body_json.get("challenge")
                if challenge:
                    logger.info(f"Slack verification challenge: {challenge}")
                    return PlainTextResponse(
                        content=challenge,
                    )
            except json.JSONDecodeError:
                logger.error("Failed to decode Slack verification request body.")
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Slack verification request."},
                )

        # Validate the agent ID from request headers
        error_response = await self.validate_agent_identity_headers(
            agent_id, request, content
        )
        if error_response:
            return error_response

        # Construct the full URL for the agent request
        agent_url = f"{agent.acp_url}/{path.lstrip('/')}"
        if request.url.query:
            agent_url += f"?{request.url.query}"
        logger.info(
            f"Forwarding request to agent {agent_id} ({agent.name}) at {agent_url}"
        )
        # Forward the request to the agent's ACP URL
        req = self.client.build_request(
            request.method,
            agent_url,
            headers=get_request_headers_to_forward(request),
            content=content,
            timeout=self.webhook_request_timeout,
        )
        r = await self.client.send(req, stream=False)
        return Response(
            r.read(),
            status_code=r.status_code,
            headers=r.headers,
            background=BackgroundTask(r.aclose),
        )

    async def validate_agent_identity_headers(
        self, agent_id: str, request: Request, content: bytes
    ) -> JSONResponse | None:
        """
        Extract and verify agent identity from request headers.
        Returns the agent ID if found, otherwise None.
        """
        if request.headers.get("X-Agent-API-Key"):
            return await self.validate_agent_api_key(agent_id, request)

        if request.headers.get("x-hub-signature-256"):
            # This is a GitHub webhook, use the API key from the ACP
            return await self.validate_github_delivery_webhook(
                agent_id, request, content
            )

        if request.headers.get("x-slack-signature"):
            # This is a Slack webhook, use the API key from the ACP
            return await self.validate_slack_delivery_webhook(
                agent_id, request, content
            )

        if self.auth_gateway_enabled:
            # If auth gateway is enabled, use it to verify the agent identity
            error_response = await verify_auth_gateway(request, self.auth_gateway)
            if error_response:
                return error_response
            # If no error response, authentication successful
            return None

        return JSONResponse(
            status_code=403,
            content={"detail": "Missing authentication for forward request."},
        )

    async def validate_agent_api_key(
        self, agent_id: str, request: Request
    ) -> JSONResponse | None:
        """
        Validate agent API key from the request headers.
        Returns None if valid, otherwise JSONResponse with error.
        """
        agent_api_key = request.headers.get("X-Agent-API-Key")
        assert agent_api_key, "Missing X-Agent-API-Key header."

        api_key_entity = await self.agent_api_key_repo.get_external_by_agent_id_and_key(
            agent_id=agent_id, api_key=agent_api_key
        )
        if not api_key_entity:
            return JSONResponse(
                status_code=401,
                content={"detail": f"Invalid API key for agent ID {agent_id}."},
            )

        return None

    async def validate_github_delivery_webhook(
        self, agent_id: str, request: Request, payload_body: bytes
    ) -> JSONResponse | None:
        """
        Validate GitHub delivery webhook for forward requests.
        Returns None if valid, otherwise JSONResponse with error.
        """
        signature_header = request.headers.get("x-hub-signature-256")
        assert signature_header, "Missing x-hub-signature-256 header."

        if not payload_body:
            error_msg = "Empty payload in GitHub webhook."
            logger.warning(error_msg)
            return JSONResponse(
                status_code=400,
                content={"detail": error_msg},
            )

        payload_json = None
        try:
            payload_json = json.loads(payload_body.decode("utf-8"))
        except json.JSONDecodeError:
            error_msg = "Failed to parse GitHub webhook payload as JSON."
            logger.warning(error_msg)
            return JSONResponse(
                status_code=400,
                content={"detail": error_msg},
            )

        if not payload_json.get("repository"):
            # Currently only supporting GitHub webhooks with repository info
            error_msg = "GitHub webhook payload missing repository info."
            logger.warning(error_msg)
            return JSONResponse(
                status_code=400,
                content={"detail": error_msg},
            )

        repository_name = payload_json["repository"].get("full_name")
        if not repository_name:
            error_msg = "GitHub webhook payload missing repository name."
            logger.warning(error_msg)
            return JSONResponse(
                status_code=400,
                content={"detail": error_msg},
            )

        api_key_entity = await self.agent_api_key_repo.get_by_agent_id_and_name(
            agent_id=agent_id, name=repository_name, api_key_type=AgentAPIKeyType.GITHUB
        )
        if not api_key_entity:
            error_msg = f"No API key found for GitHub repository {repository_name}."
            logger.warning(error_msg)
            return JSONResponse(status_code=404, content={"detail": error_msg})

        # Validate the signature
        hash_object = hmac.new(
            api_key_entity.api_key.encode("utf-8"),
            msg=payload_body,
            digestmod=hashlib.sha256,
        )
        expected_signature = "sha256=" + hash_object.hexdigest()
        if not hmac.compare_digest(expected_signature, signature_header):
            error_msg = "Invalid GitHub webhook signature"
            logger.warning(error_msg)
            return JSONResponse(status_code=401, content={"detail": error_msg})

        return None

    async def validate_slack_delivery_webhook(
        self, agent_id: str, request: Request, payload_body: bytes
    ) -> JSONResponse | None:
        """
        Validate Slack delivery webhook for forward requests.
        Returns None if valid, otherwise JSONResponse with error.
        """
        signature_header = request.headers.get("x-slack-signature")
        assert signature_header, "Missing x-slack-signature header."

        request_timestamp_raw = request.headers.get("X-Slack-Request-Timestamp")
        if not request_timestamp_raw:
            error_msg = "Missing X-Slack-Request-Timestamp header."
            logger.warning(error_msg)
            return JSONResponse(
                status_code=401,
                content={"detail": error_msg},
            )
        request_timestamp = 0
        try:
            request_timestamp = int(request_timestamp_raw)
        except ValueError:
            error_msg = "Invalid X-Slack-Request-Timestamp header value."
            logger.warning(error_msg)
            return JSONResponse(
                status_code=400,
                content={"detail": error_msg},
            )
        # Check if the request timestamp is within a reasonable range (5 minutes)
        # to prevent replay attacks
        if abs(time.time() - request_timestamp) > 60 * 5:
            error_msg = "Slack webhook request has bad timestamp."
            logger.warning(error_msg)
            return JSONResponse(
                status_code=400,
                content={"detail": error_msg},
            )

        # We already checked that the payload is not empty and parseable when looking for the challenge, so we can decode it
        payload_json = json.loads(payload_body.decode("utf-8"))
        if not payload_json.get("api_app_id"):
            # Currently only supporting Slack webhooks with API app ID
            error_msg = "Slack webhook payload missing API app ID."
            logger.warning(error_msg)
            return JSONResponse(
                status_code=400,
                content={"detail": error_msg},
            )

        api_app_id = payload_json["api_app_id"]
        api_key_entity = await self.agent_api_key_repo.get_by_agent_id_and_name(
            agent_id=agent_id, name=api_app_id, api_key_type=AgentAPIKeyType.SLACK
        )
        if not api_key_entity:
            error_msg = f"No API key found for Slack app {api_app_id}."
            logger.warning(error_msg)
            return JSONResponse(status_code=404, content={"detail": error_msg})

        # Validate the signature
        hash_object = hmac.new(
            api_key_entity.api_key.encode("utf-8"),
            msg=f"v0:{request_timestamp}:".encode() + payload_body,
            digestmod=hashlib.sha256,
        )
        expected_signature = "v0=" + hash_object.hexdigest()
        if not hmac.compare_digest(expected_signature, signature_header):
            error_msg = "Invalid Slack webhook signature"
            logger.warning(error_msg)
            return JSONResponse(status_code=401, content={"detail": error_msg})

        return None


DAgentAPIKeysUseCase = Annotated[AgentAPIKeysUseCase, Depends(AgentAPIKeysUseCase)]
