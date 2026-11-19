"""Access checks on the Slack Socket Mode settings routes."""

from unittest.mock import AsyncMock, MagicMock

import pytest
import src.api.routes.agent_api_keys as mod
from src.adapters.authorization.exceptions import AuthorizationError
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.api.schemas.agent_api_keys import SetSlackSocketModeRequest
from src.utils.agent_api_key_authorization import API_KEY_NOT_FOUND_MESSAGE

MISSING = ItemDoesNotExist("Item with id 'key-1' does not exist.")


def _set(use_case, authorization):
    return mod.set_slack_socket_mode(
        id="key-1",
        request=SetSlackSocketModeRequest(app_token="xapp-1", forward_path="slack"),
        agent_api_key_use_case=use_case,
        authorization_service=authorization,
    )


def _delete(use_case, authorization):
    return mod.delete_slack_socket_mode(
        id="key-1",
        agent_api_key_use_case=use_case,
        authorization_service=authorization,
    )


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("route", [_set, _delete], ids=["put", "delete"])
@pytest.mark.parametrize(
    ("readable", "stored"),
    [
        pytest.param(False, MagicMock(id="key-1"), id="another-accounts-key"),
        pytest.param(False, MISSING, id="no-such-key"),
        # An access grant left behind for a key that is gone.
        pytest.param(True, MISSING, id="stale-grant"),
    ],
)
async def test_a_key_the_caller_cannot_see_looks_the_same_as_a_missing_one(
    route, readable, stored
):
    # Different 404s would tell a caller whether another account's key exists.
    authorization = MagicMock()
    authorization.check = AsyncMock(
        side_effect=None if readable else AuthorizationError("denied")
    )
    use_case = MagicMock()
    use_case.get = AsyncMock(
        side_effect=stored if isinstance(stored, Exception) else None,
        return_value=stored,
    )

    with pytest.raises(ItemDoesNotExist) as exc:
        await route(use_case, authorization)

    assert str(exc.value.message) == API_KEY_NOT_FOUND_MESSAGE
