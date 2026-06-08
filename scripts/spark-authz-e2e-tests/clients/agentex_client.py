"""REST client for scale-agentex.

Thin httpx wrapper scoped to the endpoints AGX1-325 exercises:
agent (create / delete) + agent_api_keys (create / get / get-by-name / list /
delete / delete-by-name). Each method returns the raw httpx.Response so
callers can assert on status codes directly.

Auth: scale-agentex's middleware forwards request headers to ``agentex-auth``
for verification. Whatever ``agentex-auth`` accepts in the target environment
(an API key, a bearer token, etc.) gets passed through ``IdentityCredentials.
headers`` as-is.
"""

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IdentityCredentials:
    """Headers + account + user identifiers for one identity."""

    headers: dict[str, str]
    identity_id: str
    account_id: str
    subject_type: str = "identity"

    def principal_context(self) -> dict:
        identity_key = (
            "service_account_id"
            if self.subject_type == "service_identity"
            else "user_id"
        )
        return {
            identity_key: self.identity_id,
            "account_id": self.account_id,
            "metadata": {},
        }


class AgentexClient:
    """HTTP client for one identity's perspective on scale-agentex."""

    def __init__(
        self,
        base_url: str,
        credentials: IdentityCredentials,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self.credentials = credentials
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            headers=credentials.headers,
        )

    # ------------------------------------------------------------------
    # Agents (parent resource — api_keys hang off an agent)
    # ------------------------------------------------------------------
    def create_agent(self, name: str) -> httpx.Response:
        # ``POST /agents/register-build`` (not /register) — pre-deploy
        # registration with no ACP URL or handshake. The agent lands in
        # BUILD_ONLY status, which is enough for FGAC-resource tests:
        # api_keys still hang off it, events still delegate to it.
        # ``name`` must match ``^[a-z0-9-]+$`` (no underscores).
        payload = {
            "name": name,
            "description": "E2E test agent for AGX1-325/331",
        }
        resp = self._client.post("/agents/register-build", json=payload)
        logger.debug("create_agent %s -> %d", name, resp.status_code)
        return resp

    def create_ready_agent(self, name: str) -> httpx.Response:
        payload = {
            "name": name,
            "description": "E2E test agent for AGX1-327",
            "acp_url": "http://127.0.0.1:1",
            "acp_type": "sync",
            "principal_context": self.credentials.principal_context(),
        }
        resp = self._client.post("/agents/register", json=payload)
        logger.debug("create_ready_agent %s -> %d", name, resp.status_code)
        return resp

    def delete_agent(self, agent_id: str) -> httpx.Response:
        resp = self._client.delete(f"/agents/{agent_id}")
        logger.debug("delete_agent %s -> %d", agent_id, resp.status_code)
        return resp

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------
    def create_task(
        self,
        agent_id: str,
        name: str,
        task_metadata: dict | None = None,
    ) -> httpx.Response:
        payload = {
            "jsonrpc": "2.0",
            "id": name,
            "method": "task/create",
            "params": {
                "name": name,
                "task_metadata": task_metadata,
            },
        }
        resp = self._client.post(f"/agents/{agent_id}/rpc", json=payload)
        logger.debug("create_task %s -> %d", name, resp.status_code)
        return resp

    def delete_task(self, task_id: str) -> httpx.Response:
        resp = self._client.delete(f"/tasks/{task_id}")
        logger.debug("delete_task %s -> %d", task_id, resp.status_code)
        return resp

    # ------------------------------------------------------------------
    # States (task child resource)
    # ------------------------------------------------------------------
    def create_state(
        self,
        task_id: str,
        agent_id: str,
        state: dict,
    ) -> httpx.Response:
        payload = {
            "task_id": task_id,
            "agent_id": agent_id,
            "state": state,
        }
        resp = self._client.post("/states", json=payload)
        logger.debug("create_state task=%s -> %d", task_id, resp.status_code)
        return resp

    def get_state(self, state_id: str) -> httpx.Response:
        resp = self._client.get(f"/states/{state_id}")
        logger.debug("get_state %s -> %d", state_id, resp.status_code)
        return resp

    def list_states(
        self,
        agent_id: str | None = None,
        task_id: str | None = None,
        limit: int = 50,
        page_number: int = 1,
    ) -> httpx.Response:
        params: dict = {
            "limit": limit,
            "page_number": page_number,
        }
        if agent_id is not None:
            params["agent_id"] = agent_id
        if task_id is not None:
            params["task_id"] = task_id
        resp = self._client.get("/states", params=params)
        logger.debug(
            "list_states agent=%s task=%s -> %d",
            agent_id,
            task_id,
            resp.status_code,
        )
        return resp

    def delete_state(self, state_id: str) -> httpx.Response:
        resp = self._client.delete(f"/states/{state_id}")
        logger.debug("delete_state %s -> %d", state_id, resp.status_code)
        return resp

    # ------------------------------------------------------------------
    # API keys
    # ------------------------------------------------------------------
    def create_api_key(
        self,
        agent_id: str,
        name: str,
        api_key_type: str = "external",
        api_key: str | None = None,
    ) -> httpx.Response:
        payload: dict = {
            "agent_id": agent_id,
            "name": name,
            "api_key_type": api_key_type,
        }
        if api_key is not None:
            payload["api_key"] = api_key
        resp = self._client.post("/agent_api_keys", json=payload)
        logger.debug("create_api_key %s -> %d", name, resp.status_code)
        return resp

    def get_api_key(self, api_key_id: str) -> httpx.Response:
        resp = self._client.get(f"/agent_api_keys/{api_key_id}")
        logger.debug("get_api_key %s -> %d", api_key_id, resp.status_code)
        return resp

    def get_api_key_by_name(
        self,
        name: str,
        agent_id: str,
        api_key_type: str = "external",
    ) -> httpx.Response:
        params = {"agent_id": agent_id, "api_key_type": api_key_type}
        resp = self._client.get(f"/agent_api_keys/name/{name}", params=params)
        logger.debug("get_api_key_by_name %s -> %d", name, resp.status_code)
        return resp

    def list_api_keys(
        self,
        agent_id: str,
        limit: int = 50,
        page_number: int = 1,
    ) -> httpx.Response:
        params = {
            "agent_id": agent_id,
            "limit": limit,
            "page_number": page_number,
        }
        resp = self._client.get("/agent_api_keys", params=params)
        logger.debug("list_api_keys agent=%s -> %d", agent_id, resp.status_code)
        return resp

    def delete_api_key(self, api_key_id: str) -> httpx.Response:
        resp = self._client.delete(f"/agent_api_keys/{api_key_id}")
        logger.debug("delete_api_key %s -> %d", api_key_id, resp.status_code)
        return resp

    def delete_api_key_by_name(
        self,
        name: str,
        agent_id: str,
        api_key_type: str = "external",
    ) -> httpx.Response:
        params = {"agent_id": agent_id, "api_key_type": api_key_type}
        resp = self._client.delete(f"/agent_api_keys/name/{name}", params=params)
        logger.debug("delete_api_key_by_name %s -> %d", name, resp.status_code)
        return resp

    def close(self) -> None:
        self._client.close()
