import pytest
from pydantic import ValidationError
from src.api.schemas.states import UpdateStateRequest


@pytest.mark.unit
def test_update_state_request_accepts_state_only():
    request = UpdateStateRequest.model_validate({"state": {"status": "new"}})

    assert request.state == {"status": "new"}


@pytest.mark.unit
def test_update_state_request_rejects_parent_identifiers():
    with pytest.raises(ValidationError) as exc_info:
        UpdateStateRequest.model_validate(
            {
                "state": {"status": "new"},
                "task_id": "task-1",
                "agent_id": "agent-1",
            }
        )

    errors = exc_info.value.errors()
    assert {error["loc"] for error in errors} == {("task_id",), ("agent_id",)}
    assert {error["type"] for error in errors} == {"extra_forbidden"}
