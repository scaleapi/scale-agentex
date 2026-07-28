"""Unit tests for the end_user_id RPC field.

end_user_id exists so a caller can attribute a request to an end user without
that identifier having to be threaded through agent business logic. It is
deliberately available on *every* method rather than only task/create, because
task_metadata (the pre-existing carrier) is only accepted at task creation and
is ignored on get-or-create by name, which leaves message/send-driven agents and
shared named tasks with no way to attribute the current caller.

The field is wire-only: it is not persisted on the task row, so every call that
should be attributed has to carry it.
"""

import pytest
from pydantic import ValidationError
from src.api.schemas.agents_rpc import (
    END_USER_ID_MAX_LENGTH,
    AgentRPCMethod,
    AgentRPCRequest,
)
from src.domain.entities.agents_rpc import AgentRPCRequestEntity

_TEXT_CONTENT = {"author": "user", "type": "text", "content": "hello"}

_PARAMS_BY_METHOD = {
    AgentRPCMethod.TASK_CREATE: {"name": "task-1", "params": {"a": 1}},
    AgentRPCMethod.TASK_CANCEL: {"task_id": "task-1"},
    AgentRPCMethod.MESSAGE_SEND: {"task_id": "task-1", "content": _TEXT_CONTENT},
    AgentRPCMethod.EVENT_SEND: {"task_id": "task-1", "content": _TEXT_CONTENT},
}


def _request(method: AgentRPCMethod, **extra_params) -> AgentRPCRequest:
    return AgentRPCRequest(
        jsonrpc="2.0",
        id=1,
        method=method,
        params={**_PARAMS_BY_METHOD[method], **extra_params},
    )


class TestEndUserIdOnRequestSchemas:
    @pytest.mark.parametrize("method", list(_PARAMS_BY_METHOD))
    def test_accepted_on_every_method(self, method: AgentRPCMethod):
        assert (
            _request(method, end_user_id="user-a").params.root.end_user_id == "user-a"
        )

    @pytest.mark.parametrize("method", list(_PARAMS_BY_METHOD))
    def test_defaults_to_none_when_omitted(self, method: AgentRPCMethod):
        assert _request(method).params.root.end_user_id is None

    @pytest.mark.parametrize("method", list(_PARAMS_BY_METHOD))
    def test_rejects_over_length_value(self, method: AgentRPCMethod):
        # Bounded because Temporal agents copy the value into activity headers,
        # and therefore into workflow history, on every activity invocation.
        with pytest.raises(ValidationError):
            _request(method, end_user_id="x" * (END_USER_ID_MAX_LENGTH + 1))

    @pytest.mark.parametrize("method", list(_PARAMS_BY_METHOD))
    def test_accepts_value_at_length_limit(self, method: AgentRPCMethod):
        value = "x" * END_USER_ID_MAX_LENGTH
        assert _request(method, end_user_id=value).params.root.end_user_id == value


class TestEndUserIdSurvivesEntityConversion:
    """from_api_request maps each method's params field-by-field, so a new field
    is silently dropped unless it is added to every branch."""

    @pytest.mark.parametrize("method", list(_PARAMS_BY_METHOD))
    def test_mapped_for_every_method(self, method: AgentRPCMethod):
        entity = AgentRPCRequestEntity.from_api_request(
            _request(method, end_user_id="user-a")
        )
        assert entity.params.end_user_id == "user-a"

    @pytest.mark.parametrize("method", list(_PARAMS_BY_METHOD))
    def test_none_when_omitted(self, method: AgentRPCMethod):
        entity = AgentRPCRequestEntity.from_api_request(_request(method))
        assert entity.params.end_user_id is None
