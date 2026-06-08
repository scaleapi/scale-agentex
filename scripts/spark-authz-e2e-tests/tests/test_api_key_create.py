"""AGX1-325 — Create: dual-write to SpiceDB with parent_agent edge.

Verifies that ``POST /agent_api_keys`` calls ``register_resource`` on the
authorization service, including the ``parent_agent`` edge so the cascade
``api_key.read = ... & parent_agent->read`` resolves end-to-end.
"""

import pytest

API_KEY_RESOURCE_TYPE = "api_key"


@pytest.mark.e2e
class TestApiKeyCreate:
    def test_create_registers_owner_in_spicedb(
        self, create_agent, create_api_key, authz_client, user_a
    ):
        """Owner has ``read`` and ``delete`` on the api_key right after create."""
        agent_id, _ = create_agent()
        api_key_id, _, _ = create_api_key(agent_id)

        # Owner cascade: register_resource(parent=agent) wrote the parent_agent
        # edge; without it, every read/delete check fails closed.
        assert authz_client.check_permission_bool(
            user_a.identity_id, API_KEY_RESOURCE_TYPE, api_key_id, "read"
        )
        assert authz_client.check_permission_bool(
            user_a.identity_id, API_KEY_RESOURCE_TYPE, api_key_id, "delete"
        )

    def test_non_owner_has_no_permissions(
        self, create_agent, create_api_key, authz_client, user_b
    ):
        """A same-tenant user with no grant sees no permissions on the api_key."""
        agent_id, _ = create_agent()
        api_key_id, _, _ = create_api_key(agent_id)

        for permission in ("read", "delete"):
            assert not authz_client.check_permission_bool(
                user_b.identity_id, API_KEY_RESOURCE_TYPE, api_key_id, permission
            ), f"user_b should not have {permission} on api_key {api_key_id}"
