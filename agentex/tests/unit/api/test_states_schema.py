import pytest
from src.api.schemas.states import UpdateStateRequest


@pytest.mark.unit
def test_update_state_request_accepts_state_only():
    request = UpdateStateRequest.model_validate({"state": {"status": "new"}})

    assert request.state == {"status": "new"}


@pytest.mark.unit
def test_update_state_request_ignores_legacy_parent_identifiers():
    request = UpdateStateRequest.model_validate(
        {
            "state": {"status": "new"},
            "task_id": "task-1",
            "agent_id": "agent-1",
        }
    )

    assert request.model_dump() == {"state": {"status": "new"}}
