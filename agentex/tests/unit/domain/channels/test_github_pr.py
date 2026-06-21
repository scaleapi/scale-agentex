"""Unit tests for the GitHub/Gitea PR channel shaper."""

from __future__ import annotations

import json

import pytest
from src.domain.channels.github_pr import GitHubPRChannel

_CHANNEL = GitHubPRChannel()


def _pr_body(**pr_overrides) -> dict:
    pr = {
        "number": 42,
        "title": "Add config-by-id",
        "body": "This PR wires config-by-id into the channel binding.",
        "html_url": "https://example.com/org/repo/pull/42",
    }
    pr.update(pr_overrides)
    return {
        "action": "opened",
        "repository": {"full_name": "org/repo"},
        "sender": {"login": "octocat"},
        "pull_request": pr,
    }


class TestToInbound:
    def test_shapes_pr_into_clean_prompt(self):
        inbound = _CHANNEL.to_inbound("pr-review", _pr_body())
        assert inbound.channel == "github_pr"
        assert "Pull request org/repo#42: Add config-by-id" in inbound.text
        assert "Action: opened" in inbound.text
        assert "https://example.com/org/repo/pull/42" in inbound.text
        assert "This PR wires config-by-id" in inbound.text

    def test_peer_id_is_repo_and_number_so_repeat_events_fold(self):
        # Same PR, different actions -> same peer_id -> same task (get-or-create).
        opened = _CHANNEL.to_inbound("pr-review", _pr_body(number=7))
        synced = _CHANNEL.to_inbound(
            "pr-review", {**_pr_body(number=7), "action": "synchronize"}
        )
        assert opened.peer_id == "org/repo#7"
        assert opened.peer_id == synced.peer_id

    def test_sender_is_the_pr_actor(self):
        inbound = _CHANNEL.to_inbound("pr-review", _pr_body())
        assert inbound.sender_id == "octocat"

    def test_inline_diff_is_included_when_present(self):
        body = _pr_body()
        body["diff"] = "diff --git a/x b/x\n+added line"
        inbound = _CHANNEL.to_inbound("pr-review", body)
        assert "Diff:" in inbound.text
        assert "+added line" in inbound.text

    def test_diff_is_truncated(self):
        body = _pr_body()
        body["diff"] = "x" * 50000
        inbound = _CHANNEL.to_inbound("pr-review", body)
        # 30k cap + the surrounding prompt scaffolding, well under the raw 50k.
        assert len(inbound.text) < 40000

    def test_non_pr_payload_falls_back_to_generic_rendering(self):
        # A ping / non-PR event has no pull_request; PR shaping is skipped and the
        # generic webhook rendering applies (raw JSON), not a "Pull request ..." prompt.
        body = {"zen": "Keep it logically awesome.", "hook_id": 1}
        inbound = _CHANNEL.to_inbound("pr-review", body)
        assert "Keep it logically awesome." in inbound.text
        assert "Pull request" not in inbound.text

    def test_missing_repo_full_name_still_keys_on_number(self):
        body = _pr_body()
        body.pop("repository")
        inbound = _CHANNEL.to_inbound("pr-review", body)
        assert inbound.peer_id == "pr#42"


class TestAuthInheritedFromWebhook:
    def test_uses_hmac_sha256_auth(self):
        # GitHubPRChannel reuses WebhookChannel's sha256= HMAC verification.
        import hashlib
        import hmac

        from src.domain.channels.base import ChannelBinding

        secret = "topsecret"
        raw = json.dumps(_pr_body()).encode()
        sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()

        class _Req:
            def __init__(self, headers):
                self.headers = headers

        binding = ChannelBinding(secret=secret, agent_name="review-agent", channel="github_pr")
        good = _Req({"x-hub-signature-256": sig})
        bad = _Req({"x-hub-signature-256": "sha256=deadbeef"})
        assert _CHANNEL.authenticate(binding, good, raw) is True
        assert _CHANNEL.authenticate(binding, bad, raw) is False


@pytest.fixture(autouse=True)
def _clear_routes_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CHANNELS_WEBHOOK_ROUTES", raising=False)
    yield
