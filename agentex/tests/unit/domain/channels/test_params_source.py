"""Unit tests for remote params resolution + task_metadata stamping.

The channel layer stays generic: a binding either carries inline params or a
`params_source` URL it GETs and forwards verbatim. These tests cover that resolution,
the route-store parsing, and metadata stamping on dispatch.
"""

from __future__ import annotations

import json

import pytest
from src.domain.channels.base import ChannelBinding, InboundMessage
from src.domain.channels.params_source import (
    ParamsSourceError,
    resolve_binding_params,
)
from src.domain.channels.router import ChannelRouter
from src.domain.entities.agents import ACPType
from src.domain.entities.agents_rpc import AgentRPCMethod


class TestResolveBindingParams:
    async def test_remote_source_populates_params_and_metadata(self):
        binding = ChannelBinding(
            secret="s", agent_name="agent-1", params_source="https://host/resolve/abc"
        )
        captured: list[str] = []

        async def fake_fetch(url: str) -> dict:
            captured.append(url)
            return {
                "params": {"system_prompt": "from source", "model": "some-model"},
                "task_metadata": {"trace": "xyz"},
            }

        resolved = await resolve_binding_params(binding, fetch=fake_fetch)

        assert captured == ["https://host/resolve/abc"]
        assert resolved.params == {
            "system_prompt": "from source",
            "model": "some-model",
        }
        assert resolved.extra_task_metadata == {"trace": "xyz"}

    async def test_bare_object_response_is_treated_as_params(self):
        binding = ChannelBinding(
            secret="s", agent_name="agent-1", params_source="https://host/resolve/abc"
        )

        async def fake_fetch(_url: str) -> dict:
            return {"system_prompt": "bare", "model": "m"}

        resolved = await resolve_binding_params(binding, fetch=fake_fetch)
        assert resolved.params == {"system_prompt": "bare", "model": "m"}
        assert resolved.extra_task_metadata == {}

    async def test_bare_object_still_captures_task_metadata_and_strips_it(self):
        # A source that returns task_metadata without a "params" wrapper: the metadata
        # is stamped, not leaked into params.
        binding = ChannelBinding(
            secret="s", agent_name="agent-1", params_source="https://host/resolve/abc"
        )

        async def fake_fetch(_url: str) -> dict:
            return {"system_prompt": "bare", "task_metadata": {"trace": "xyz"}}

        resolved = await resolve_binding_params(binding, fetch=fake_fetch)
        assert resolved.params == {"system_prompt": "bare"}
        assert resolved.extra_task_metadata == {"trace": "xyz"}

    async def test_inline_binding_is_left_untouched_and_does_not_fetch(self):
        binding = ChannelBinding(
            secret="s", agent_name="agent-1", params={"system_prompt": "one-off"}
        )

        async def fail_fetch(_url: str) -> dict:
            raise AssertionError("fetch must not be called for inline bindings")

        resolved = await resolve_binding_params(binding, fetch=fail_fetch)
        assert resolved.params == {"system_prompt": "one-off"}

    async def test_non_object_response_raises(self):
        binding = ChannelBinding(
            secret="s", agent_name="agent-1", params_source="https://host/resolve/abc"
        )

        async def fake_fetch(_url: str):
            return ["not", "an", "object"]

        with pytest.raises(ParamsSourceError):
            await resolve_binding_params(binding, fetch=fake_fetch)


class TestWebhookBindingParse:
    def test_parses_params_source_and_channel(self, monkeypatch: pytest.MonkeyPatch):
        from src.api.routes.channels import _webhook_binding

        monkeypatch.setenv(
            "CHANNELS_WEBHOOK_ROUTES",
            json.dumps(
                {
                    "pr-review": {
                        "secret": "shh",
                        "agent_name": "agent-1",
                        "channel": "github_pr",
                        "params_source": "https://host/resolve/abc",
                    }
                }
            ),
        )
        binding = _webhook_binding("pr-review")
        assert binding is not None
        assert binding.channel == "github_pr"
        assert binding.params_source == "https://host/resolve/abc"
        assert binding.params == {}

    def test_inline_params_route_has_no_source(self, monkeypatch: pytest.MonkeyPatch):
        from src.api.routes.channels import _webhook_binding

        monkeypatch.setenv(
            "CHANNELS_WEBHOOK_ROUTES",
            json.dumps(
                {
                    "demo": {
                        "secret": "shh",
                        "agent_name": "agent-1",
                        "params": {"system_prompt": "hi"},
                    }
                }
            ),
        )
        binding = _webhook_binding("demo")
        assert binding is not None
        assert binding.params_source is None
        assert binding.params == {"system_prompt": "hi"}


class _FakeACP:
    """Records handle_rpc_request calls; returns a task on create, [] on message/send."""

    def __init__(self, task_id: str = "task-1"):
        self.calls: list[tuple] = []
        self._task_id = task_id

    async def handle_rpc_request(self, *, method, params, agent_name, request_headers):
        self.calls.append((method, params))
        if method == AgentRPCMethod.TASK_CREATE:
            return type("_Task", (), {"id": self._task_id})()
        return []

    def task_metadata_of_create(self) -> dict:
        for method, params in self.calls:
            if method == AgentRPCMethod.TASK_CREATE:
                return params.task_metadata
        raise AssertionError("no TASK_CREATE call recorded")


class TestDispatchStampsExtraMetadata:
    async def test_extra_task_metadata_is_stamped_on_task(self):
        acp = _FakeACP()
        router = ChannelRouter(acp, task_message_service=object())
        binding = ChannelBinding(
            secret="s",
            agent_name="agent-1",
            params={"system_prompt": "x"},
            extra_task_metadata={"trace": "xyz"},
        )
        inbound = InboundMessage(
            text="hi", channel="webhook", route_id="r", peer_id="r"
        )

        await router.dispatch(inbound, binding, ACPType.SYNC)

        metadata = acp.task_metadata_of_create()
        assert metadata["trace"] == "xyz"
        assert metadata["channel"] == "webhook"
        assert metadata["route_id"] == "r"

    async def test_binding_without_extra_metadata_omits_it(self):
        acp = _FakeACP()
        router = ChannelRouter(acp, task_message_service=object())
        binding = ChannelBinding(
            secret="s", agent_name="agent-1", params={"system_prompt": "x"}
        )
        inbound = InboundMessage(
            text="hi", channel="webhook", route_id="r", peer_id="r"
        )

        await router.dispatch(inbound, binding, ACPType.SYNC)

        metadata = acp.task_metadata_of_create()
        assert "trace" not in metadata
        assert set(metadata) == {"channel", "route_id", "peer_id", "sender_id"}

    async def test_extra_metadata_cannot_override_canonical_keys(self):
        acp = _FakeACP()
        router = ChannelRouter(acp, task_message_service=object())
        # A malicious/misconfigured source tries to spoof the canonical channel field.
        binding = ChannelBinding(
            secret="s",
            agent_name="agent-1",
            params={"system_prompt": "x"},
            extra_task_metadata={"channel": "spoofed", "trace": "ok"},
        )
        inbound = InboundMessage(
            text="hi", channel="webhook", route_id="r", peer_id="r"
        )

        await router.dispatch(inbound, binding, ACPType.SYNC)

        metadata = acp.task_metadata_of_create()
        assert metadata["channel"] == "webhook"  # canonical wins, not "spoofed"
        assert metadata["trace"] == "ok"  # non-colliding extras still stamped
