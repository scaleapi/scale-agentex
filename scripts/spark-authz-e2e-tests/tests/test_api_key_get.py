"""AGX1-325 — Get: owner 200, non-owner 404 (collapsed from 403).

Verifies the id-path and name-path GET handlers route the auth check through
``_check_api_key_or_collapse_to_404`` so denials surface as 404, hiding
cross-tenant existence.
"""

import pytest


@pytest.mark.e2e
class TestApiKeyGet:
    def test_owner_get_by_id_returns_200(
        self, parent_agent, create_api_key, agentex_client_a
    ):
        agent_id, _ = parent_agent
        api_key_id, _, _ = create_api_key(agent_id)

        resp = agentex_client_a.get_api_key(api_key_id)
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == api_key_id

    def test_owner_get_by_name_returns_200(
        self, parent_agent, create_api_key, agentex_client_a
    ):
        agent_id, _ = parent_agent
        api_key_id, api_key_name, _ = create_api_key(agent_id)

        resp = agentex_client_a.get_api_key_by_name(api_key_name, agent_id=agent_id)
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == api_key_id

    def test_non_owner_get_by_id_returns_404(
        self, parent_agent, create_api_key, agentex_client_b
    ):
        """Denial collapses to 404, not 403 — no existence leak."""
        agent_id, _ = parent_agent
        api_key_id, _, _ = create_api_key(agent_id)

        resp = agentex_client_b.get_api_key(api_key_id)
        assert (
            resp.status_code == 404
        ), f"expected 404 (collapsed), got {resp.status_code}: {resp.text}"

    def test_non_owner_get_by_name_returns_404(
        self, parent_agent, create_api_key, agentex_client_b
    ):
        """Name-route denial must also collapse to 404 with the identifier-free
        body so the absent-row and denied-row responses are indistinguishable."""
        agent_id, _ = parent_agent
        _, api_key_name, _ = create_api_key(agent_id)

        resp = agentex_client_b.get_api_key_by_name(api_key_name, agent_id=agent_id)
        assert (
            resp.status_code == 404
        ), f"expected 404 (collapsed), got {resp.status_code}: {resp.text}"
