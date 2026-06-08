"""AGX1-325 — List: owner sees own, non-owner sees filtered.

``GET /agent_api_keys?agent_id=...`` forwards ``DAuthorizedResourceIds`` into
the use-case as an ``id`` filter, so the SQL ``WHERE id IN (...)`` clause
restricts results to api_keys the caller has ``read`` on.
"""

import pytest


@pytest.mark.e2e
class TestApiKeyList:
    def test_owner_list_includes_own_api_key(
        self, parent_agent, create_api_key, agentex_client_a
    ):
        agent_id, _ = parent_agent
        api_key_id, _, _ = create_api_key(agent_id)

        resp = agentex_client_a.list_api_keys(agent_id=agent_id)
        assert resp.status_code == 200, resp.text
        ids = [k["id"] for k in resp.json()]
        assert api_key_id in ids, f"owner missing own api_key in list: {ids}"

    def test_non_owner_list_excludes_user_a_api_key(
        self, parent_agent, create_api_key, agentex_client_b
    ):
        """user_b can hit the route (they have ``read`` on the agent in the
        same tenant) but receives a list filtered to their own authorized
        api_keys — which is empty for resources owned solely by user_a."""
        agent_id, _ = parent_agent
        api_key_id, _, _ = create_api_key(agent_id)

        resp = agentex_client_b.list_api_keys(agent_id=agent_id)
        # If user_b lacks ``read`` on the agent itself the route 404s before
        # the list filter runs — the assertion below would never execute. Skip
        # explicitly so this shows as SKIPPED (not PASSED) and the gap is
        # visible in reports. To actually exercise the list filter, user_b
        # needs ``read`` on the agent but no ``read`` on user_a's api_keys.
        if resp.status_code == 404:
            pytest.skip(
                "user_b lacks read on the parent agent — route 404s before the "
                "list filter runs; FGAC list-filter behavior not exercised."
            )
        assert resp.status_code == 200, resp.text
        ids = [k["id"] for k in resp.json()]
        assert (
            api_key_id not in ids
        ), f"user_b saw user_a's api_key in list — FGAC filter leak: {ids}"
