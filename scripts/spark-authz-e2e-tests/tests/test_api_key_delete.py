"""AGX1-325 — Delete: dual-write deregisters; non-owner 404.

Verifies ``DELETE /agent_api_keys/{id}``:
 1. Deregisters the api_key from SpiceDB (owner permissions vanish post-delete).
 2. Returns 404 for a non-owner — never 403, never deletes the row.
"""

import pytest

API_KEY_RESOURCE_TYPE = "api_key"


@pytest.mark.e2e
class TestApiKeyDelete:
    def test_owner_delete_deregisters_in_spicedb(
        self,
        create_agent,
        agentex_client_a,
        authz_client,
        user_a,
    ):
        """After delete, SpiceDB no longer reports the owner relationship.

        Built without the ``create_api_key`` factory because that fixture
        registers its own teardown, which would race against the explicit
        delete inside the test.
        """
        from helpers.factories import unique_api_key_name

        agent_id, _ = create_agent()
        resp = agentex_client_a.create_api_key(
            agent_id=agent_id, name=unique_api_key_name()
        )
        assert resp.status_code in (200, 201), resp.text
        api_key_id = resp.json()["id"]

        # Sanity: owner has read pre-delete.
        assert authz_client.check_permission_bool(
            user_a.identity_id, API_KEY_RESOURCE_TYPE, api_key_id, "read"
        )

        del_resp = agentex_client_a.delete_api_key(api_key_id)
        assert del_resp.status_code in (200, 204), del_resp.text

        # Deregister happened: owner no longer has any permission.
        assert not authz_client.check_permission_bool(
            user_a.identity_id, API_KEY_RESOURCE_TYPE, api_key_id, "read"
        ), "owner still has read after delete — deregister did not fire"
        assert not authz_client.check_permission_bool(
            user_a.identity_id, API_KEY_RESOURCE_TYPE, api_key_id, "delete"
        )

    def test_non_owner_delete_returns_404_and_preserves_row(
        self,
        parent_agent,
        create_api_key,
        agentex_client_a,
        agentex_client_b,
    ):
        """user_b's denied delete must collapse to 404 and leave the row intact."""
        agent_id, _ = parent_agent
        api_key_id, _, _ = create_api_key(agent_id)

        denied = agentex_client_b.delete_api_key(api_key_id)
        assert (
            denied.status_code == 404
        ), f"expected 404 (collapsed), got {denied.status_code}: {denied.text}"

        # Row still exists: owner can still fetch it.
        owner_get = agentex_client_a.get_api_key(api_key_id)
        assert owner_get.status_code == 200, (
            f"api_key was deleted despite the auth check failing — "
            f"got {owner_get.status_code}: {owner_get.text}"
        )

    def test_non_owner_delete_by_name_returns_404(
        self,
        parent_agent,
        create_api_key,
        agentex_client_b,
    ):
        agent_id, _ = parent_agent
        _, api_key_name, _ = create_api_key(agent_id)

        resp = agentex_client_b.delete_api_key_by_name(api_key_name, agent_id=agent_id)
        assert (
            resp.status_code == 404
        ), f"expected 404 (collapsed), got {resp.status_code}: {resp.text}"
