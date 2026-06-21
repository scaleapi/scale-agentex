"""GitHubPRChannel: shape a GitHub/Gitea pull-request webhook into a clean prompt.

A thin payload-shaper on top of the generic webhook channel. It reuses
`WebhookChannel`'s `sha256=` HMAC authentication (the GitHub/Gitea
`X-Hub-Signature-256` scheme) and only overrides normalization: a PR event becomes
a single review prompt (title + body + metadata, plus an inline diff when the caller
includes one), keyed on `repo#number` so repeated events for the same PR (opened,
synchronize, reopened, ...) fold into one task instead of spawning a new one each time.

This keeps PR-specific shaping out of the generic `WebhookChannel` (which stays
source-agnostic by design). Posting the reply back as a PR comment is the outbound
half — a CI Action can call this endpoint with `?wait=true` and post the returned
review.
"""

from __future__ import annotations

from typing import Any

from src.domain.channels.base import InboundMessage
from src.domain.channels.webhook import WebhookChannel

# Keep the shaped prompt bounded — PR bodies and diffs can be large.
_MAX_BODY_CHARS = 4000
_MAX_DIFF_CHARS = 30000


class GitHubPRChannel(WebhookChannel):
    name = "github_pr"

    def to_inbound(self, route_id: str, body: dict[str, Any]) -> InboundMessage:
        pull_request = body.get("pull_request")
        if not isinstance(pull_request, dict):
            # Not a PR event (ping, issue comment, ...) — defer to generic rendering.
            return super().to_inbound(route_id, body)

        return InboundMessage(
            text=_render_pr_prompt(body, pull_request),
            channel=self.name,
            route_id=route_id,
            peer_id=_pr_peer_id(body, pull_request) or route_id,
            sender_id=_actor(body),
            raw=body,
        )


def _repo_full_name(body: dict[str, Any]) -> str | None:
    repo = body.get("repository")
    if isinstance(repo, dict):
        full_name = repo.get("full_name")
        if isinstance(full_name, str) and full_name:
            return full_name
    return None


def _pr_peer_id(body: dict[str, Any], pull_request: dict[str, Any]) -> str | None:
    """Stable per-PR conversation scope so repeat events fold into one task."""
    number = pull_request.get("number")
    repo = _repo_full_name(body)
    if repo and number is not None:
        return f"{repo}#{number}"
    if number is not None:
        return f"pr#{number}"
    return None


def _actor(body: dict[str, Any]) -> str:
    sender = body.get("sender")
    if isinstance(sender, dict):
        login = sender.get("login")
        if isinstance(login, str) and login:
            return login
    return "github"


def _inline_diff(body: dict[str, Any], pull_request: dict[str, Any]) -> str | None:
    """A diff the caller chose to inline (webhook payloads don't carry it natively)."""
    for source in (body, pull_request):
        diff = source.get("diff")
        if isinstance(diff, str) and diff.strip():
            return diff.strip()
    return None


def _render_pr_prompt(body: dict[str, Any], pull_request: dict[str, Any]) -> str:
    repo = _repo_full_name(body)
    number = pull_request.get("number")
    title = (pull_request.get("title") or "").strip()
    action = (body.get("action") or "").strip()
    description = (pull_request.get("body") or "").strip()
    html_url = pull_request.get("html_url") or pull_request.get("url")

    header = "Pull request"
    if repo and number is not None:
        header = f"Pull request {repo}#{number}"
    elif number is not None:
        header = f"Pull request #{number}"

    lines = [f"{header}: {title}" if title else header]
    if action:
        lines.append(f"Action: {action}")
    if html_url:
        lines.append(f"URL: {html_url}")
    if description:
        lines.append("")
        lines.append("Description:")
        lines.append(description[:_MAX_BODY_CHARS])

    diff = _inline_diff(body, pull_request)
    if diff:
        lines.append("")
        lines.append("Diff:")
        lines.append(diff[:_MAX_DIFF_CHARS])

    return "\n".join(lines)
