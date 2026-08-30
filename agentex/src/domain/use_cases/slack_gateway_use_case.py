"""Slack gateway — a platform-side ingress that fronts one Slack app (``@agent``)
and routes each turn to the resolved agent runtime.

Shape mirrors Scheduled Agent Runs (``scheduled_agent_run_activities``): an external
trigger that does ``task/create`` (get-or-create by name) then ``event/send`` against
an arbitrary agent via ``AgentsACPUseCase.handle_rpc_request``, with an idempotency
marker so provider retries don't double-deliver. Here the trigger is a Slack event
instead of a cron fire.

Deliberately NOT layered onto ``/agents/forward`` — that route is the generic,
per-agent verifying proxy. This is its own module so Slack-specific logic stays out
of the generic path.

Identity: a turn runs as the **invoking human** when that Slack user has an active
identity link with a usable stored credential (see ``_turn_identity``). Their stored
session credential rides on the delegation headers, becomes ``x-acting-user-cookie``
on the ACP call, and is what makes the agent's user-scoped tools resolve *their*
connected integrations — Notion, Linear, the hosted Slack MCP — rather than a shared
account's. That per-user resolution is the whole point: the secrets service derives
the owner from the caller and offers no way to ask for someone else's, so acting as
a person requires holding a credential belonging to that person.

It is their session cookie rather than a per-link API key because identity-service
allows one API key per user and every active user already has one, so minting
answers 409 and the existing key's secret cannot be read back. The session cookie is
also the better credential: it carries its own expiry, and taking it leaves the
user's existing credentials untouched. The cost is that the link ends when the
session does.

Everyone else falls back to the gateway's own bot service account
(``SLACK_GATEWAY_ACTING_BOT_API_KEY`` + ``SLACK_GATEWAY_ACCOUNT_ID``, env /
k8s-secret only), which still produces a working turn — just without personal
integrations. So user scoping is opt-in per person, and NOT an isolation guarantee
while the fallback is enabled; ``SLACK_GATEWAY_REQUIRE_LINKED_USER`` closes it.

Task keying follows the identity: a linked user gets one task per (workspace,
channel, thread, user), so each participant in a shared thread owns their own
conversation and a task never has two owners. Workspace and channel are in the key
because ``task/create`` is get-or-create on the name — two turns yielding the same
name become one task, merging their prompts, config and account context — and
``thread_ts`` is unique only within a workspace. Unlinked users keep the legacy
thread-wide key, which carries that same weakness and predates this work.

The bot's Slack credentials (signing secret, bot token) are separate from all of this
and remain shared — the gateway posts as the app, not as the user.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Annotated, Any

import httpx
from fastapi import BackgroundTasks, Depends

from src.adapters.crud_store.exceptions import DuplicateItemError, ItemDoesNotExist
from src.config.dependencies import (
    GlobalDependencies,
    database_async_read_only_session_maker,
    database_async_read_write_engine,
    database_async_read_write_session_maker,
)
from src.domain.entities.agents import ACPType, AgentStatus
from src.domain.entities.agents_rpc import (
    AgentRPCMethod,
    CreateTaskRequestEntity,
    SendEventRequestEntity,
    SendMessageRequestEntity,
)
from src.domain.entities.task_messages import (
    MessageAuthor,
    TextContentEntity,
    TextFormat,
)
from src.domain.repositories.agent_repository import AgentRepository
from src.utils.logging import make_logger

logger = make_logger(__name__)

_MENTION_RE = re.compile(r"^\s*<@[A-Z0-9]+>\s*")
# agentex agent names are hyphenated (e.g. "dbt-assistant"); the registered golden
# agent is "golden-agent", not "golden_agent" (verified against the sgp-dev directory).
_DEFAULT_AGENT_NAME = "golden-agent"

# Every Slack turn acts as the gateway's own SGP identity — a dedicated bot service
# account. Forwarded as x-api-key: the platform verifies it -> principal (authz) and
# converts it to x-acting-user-api-key downstream (tools act as the bot via
# resolve_user_secrets). The bot is its own entity, not a proxy for the invoking user;
# all Slack traffic shares its account. Env / k8s-secret only, never in code.
_ACTING_BOT_API_KEY = os.getenv("SLACK_GATEWAY_ACTING_BOT_API_KEY", "")

# Account the bot acts within. REQUIRED alongside the API key — the backend authenticates
# on (x-api-key + x-selected-account-id) together; the key alone 401s. Also forwarded
# downstream so the agent runs in this account.
_ACTING_ACCOUNT_ID = os.getenv("SLACK_GATEWAY_ACCOUNT_ID", "")

# DEV ONLY. When true, skip Slack signature verification so the backend pipeline can be
# exercised by POSTing a hand-crafted payload to /slack/events (no real Slack app yet).
# Default OFF; never enable outside a dev environment — it lets anyone invoke agents
# through the gateway unauthenticated. TODO: remove once the real Slack app is wired.
_DEV_SKIP_VERIFY = os.getenv("SLACK_GATEWAY_DEV_SKIP_VERIFY", "").lower() in (
    "1",
    "true",
    "yes",
)

_MESSAGE_PAGE = 200  # per-poll page size when collecting the reply

# What an unlinked user gets. Default OFF: an unlinked user falls back to the shared
# bot identity and still gets a working turn, just without their personal
# integrations. Turn it ON once enough of the workspace has linked.
#
# Be clear-eyed about what OFF means: with the fallback in place, running as the
# invoking human is opt-in, so it is NOT an isolation guarantee — anyone who hasn't
# linked simply inherits the bot's (much narrower) access instead.
_REQUIRE_LINKED_USER = os.getenv("SLACK_GATEWAY_REQUIRE_LINKED_USER", "").lower() in (
    "1",
    "true",
    "yes",
)

_UNLINKED_MESSAGE = (
    "I don't know who you are in SGP yet, so I can't run this as you. "
    "Connect your account and try again."
)

# Public origin for the link we DM. Must be a host the user's browser can reach AND
# a sibling subdomain of the SGP host, or their session cookie never arrives and the
# callback can't tell who they are. Unset => no offers (a broken link is worse than
# no link).
_PUBLIC_BASE_URL = os.getenv("SLACK_GATEWAY_PUBLIC_BASE_URL", "").rstrip("/")

# How long before an unlinked user is offered the link again. ``claim_send`` already
# caps DMs at 2 per live nonce, but a nonce only lives ~10 minutes, so without this a
# persistent mentioner re-arms that budget every 10 minutes. Worst case becomes ~2
# DMs an hour instead of ~12.
_LINK_OFFER_COOLDOWN_S = 3600

# Slack's HTTP Events API is at-least-once — it retries a delivery (up to ~3x, with an
# X-Slack-Retry-Num header) if we don't 200 within ~3s. Dedup on the envelope's
# ``event_id`` via Redis with a short TTL so a retry can't start a duplicate turn.
_EVENT_DEDUP_TTL_SECONDS = int(os.getenv("SLACK_EVENT_DEDUP_TTL", "600"))

# A create-race (two concurrent first turns for one thread) makes the loser's
# get-or-create raise DuplicateItemError. Retrying re-runs get-or-create; the backoff
# lets a lagging read replica catch up so the retry sees the winner's task instead of
# racing the create against the primary again. A single retry can still miss under
# replica lag, so retry a bounded number of times before surfacing the failure.
_CREATE_RACE_ATTEMPTS = max(1, int(os.getenv("SLACK_CREATE_RACE_ATTEMPTS", "4")))
_CREATE_RACE_BACKOFF_S = float(os.getenv("SLACK_CREATE_RACE_BACKOFF_S", "0.25"))

# The ``@agent <selector>`` token drives resolution (see ``_resolve_target``): the
# selector is tried as an SGP agent_config NAME (-> golden-agent + that config), then as a
# registered agentex agent name (-> route to that runtime); if neither matches (or there's
# no selector) the turn falls back to this default agent_config id. golden-agent resolves
# whatever config_id it gets -> full turn config (prompt / model / harness / tools).
_DEFAULT_CONFIG_ID = os.getenv(
    "SLACK_GATEWAY_DEFAULT_CONFIG_ID", "416f61d9-9587-46be-a1d8-0b0aba17eb6e"
)
# SGP API base for name -> config_id resolution (GET {base}/v5/agent_configs?name=).
# Empty (or no acting identity to authenticate the call) -> name resolution is skipped.
_SGP_BASE_URL = os.getenv("SLACK_GATEWAY_SGP_BASE_URL", "").rstrip("/")
# name -> config_id, keyed by (account_id, name). Module-level because the use case is
# instantiated per-request; config ids are stable, so a process-lifetime cache is fine.
_CONFIG_ID_CACHE: dict[tuple[str, str], str] = {}

# v1/dev: MCP tools to enable per task (golden-agent switches MCPs on from the config's
# `mcps` list; the credential existing isn't enough — the tool must be enabled for the
# task). Comma-separated MCPServer names, e.g. SLACK_GATEWAY_DEFAULT_MCPS=Slack.
# TODO: comes from the resolved agent_config once tier-2 lands.
_DEFAULT_MCPS = [
    m.strip()
    for m in os.getenv("SLACK_GATEWAY_DEFAULT_MCPS", "").split(",")
    if m.strip()
]


# --------------------------------------------------------------------------- shaping


@dataclass
class InboundSlack:
    team_id: str
    channel: str
    user: str
    text: str  # mention stripped
    thread_ts: str  # session key
    selector: str | None  # first token after the mention (candidate name)


def normalize(payload: dict[str, Any]) -> InboundSlack | None:
    """Shape an app_mention / message event. Returns None for events we ignore."""
    event = payload.get("event") or {}
    if event.get("type") not in ("app_mention", "message"):
        return None
    if event.get("bot_id") or event.get("subtype"):  # ignore our own / edited / system
        return None

    text = _MENTION_RE.sub("", event.get("text") or "").strip()
    return InboundSlack(
        team_id=payload.get("team_id") or "",
        channel=event.get("channel") or event.get("channel_id") or "",
        user=event.get("user") or "",
        text=text,
        thread_ts=event.get("thread_ts") or event.get("ts") or "",
        selector=text.split(maxsplit=1)[0] if text else None,
    )


def verify_signature(
    signing_secret: str, timestamp: str, signature: str, body: bytes
) -> bool:
    """Slack v0 HMAC (same scheme as validate_slack_delivery_webhook), with a ±5 min
    replay guard. The signing secret comes from the secrets microservice, not the DB."""
    try:
        if abs(time.time() - int(timestamp)) > 60 * 5:
            return False
    except (TypeError, ValueError):
        return False
    basis = b"v0:" + timestamp.encode() + b":" + body
    expected = (
        "v0=" + hmac.new(signing_secret.encode(), basis, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, signature or "")


@dataclass
class Target:
    agent_name: str
    config_id: str | None = None

    def label(self) -> str:
        # User-facing attribution — the agent name only; the config_id (a UUID) is kept
        # out of Slack messages and recorded in task_metadata instead.
        return self.agent_name


def _strip_selector(text: str, selector: str) -> str:
    """Drop the leading selector token once it has matched a target."""
    stripped = text.strip()
    if stripped.lower().startswith(selector.lower()):
        stripped = stripped[len(selector) :].lstrip()
    return stripped


def _turn_content(
    inbound: InboundSlack, prompt: str, *, self_posts: bool = False
) -> str:
    """Prepend the Slack conversation context to the turn.

    normalize() is otherwise lossy — it hands the agent only the prompt text and drops
    the channel/thread. But to read channel history the agent needs the channel id to
    point its Slack tools at, so we prefix a short, clearly-delimited context line and
    put the user's message after a blank line. Harmless when no Slack tool is enabled.

    ``self_posts`` is set for agents the gateway does NOT relay (golden-agent, which has
    Slack write tools). For them we add an explicit directive to post their own reply
    into this thread, because nothing is delivered on their behalf — without it the turn
    would run and produce text that never reaches Slack."""
    context = (
        f"[Slack context] channel_id={inbound.channel} thread_ts={inbound.thread_ts}. "
        f"This message came from that Slack thread; to read earlier messages or the "
        f"channel's history, use your Slack tools with this channel_id."
    )
    if self_posts:
        context += (
            " IMPORTANT: your text response is NOT posted to Slack for you. Deliver your "
            f"reply by calling post_message(channel_id={inbound.channel}, "
            f"thread_ts={inbound.thread_ts}, ...). Posting a message HIDES the 'thinking…' "
            "indicator, so if a turn produces MORE THAN ONE message, call "
            f"set_status(channel_id={inbound.channel}, thread_ts={inbound.thread_ts}, "
            "status='is thinking…') right after each message that is NOT your final one; "
            "do NOT call it after your final message, so the indicator clears there. Use "
            "post_message for other channels/DMs too; only this thread's reply is your "
            "responsibility to post."
        )
    return f"{context}\n\n{prompt}"


def _agents_list_response(agents) -> dict:
    """Ephemeral Slack slash-command body listing the invocable agents. Agents are
    (name, description) pairs; empty list => a friendly 'none' message."""
    if agents:
        lines = "\n".join(f"• `@agent {a.name}` — {a.description}" for a in agents)
    else:
        lines = "_No agents are currently available._"
    text = (
        "*Available agents*\n"
        f"Mention `@agent <name>` to route to one; anything else goes to the default "
        f"*{_DEFAULT_AGENT_NAME}*.\n\n{lines}"
    )
    return {"response_type": "ephemeral", "text": text}


_AGENTS_MODAL_CALLBACK = "agents_modal"


def _build_agents_modal(agents, channel_id: str) -> dict:
    """Block Kit view for the /agents picker: a dropdown of invocable agents + a
    message box. ``channel_id`` rides in ``private_metadata`` so the view_submission
    knows where to post. The selected value is the agent name, which the submission
    handler feeds into the SAME selector->target resolution as an @mention."""
    options = [
        {
            "text": {"type": "plain_text", "text": a.name[:75]},
            "value": a.name[:75],
            **(
                {"description": {"type": "plain_text", "text": a.description[:75]}}
                if getattr(a, "description", None)
                else {}
            ),
        }
        for a in agents[:100]  # Slack static_select caps at 100 options
    ]
    return {
        "type": "modal",
        "callback_id": _AGENTS_MODAL_CALLBACK,
        "private_metadata": channel_id,
        "title": {"type": "plain_text", "text": "Ask an agent"},
        "submit": {"type": "plain_text", "text": "Send"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "agent_block",
                "label": {"type": "plain_text", "text": "Agent"},
                "element": {
                    "type": "static_select",
                    "action_id": "agent_select",
                    "placeholder": {"type": "plain_text", "text": "Choose an agent"},
                    "options": options,
                },
            },
            {
                "type": "input",
                "block_id": "message_block",
                "label": {"type": "plain_text", "text": "Message"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "message_input",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "What do you want the agent to do?",
                    },
                },
            },
        ],
    }


def _agent_text(messages) -> str | None:
    """Join agent-authored text content from a list of task messages."""
    parts = []
    for m in messages:
        content = getattr(m, "content", None)
        if (
            content is not None
            and getattr(content, "author", None) == MessageAuthor.AGENT
            and isinstance(getattr(content, "content", None), str)
        ):
            text = content.content.strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts) if parts else None


async def slack_user_profile(user_id: str) -> dict[str, str | None]:
    """``{"display_name": …, "email": …, "error": …}`` for a Slack user.

    All three can be None. ``display_name`` only makes the confirmation page legible.
    ``email`` requires the ``users:read.email`` scope, which may not be granted —
    ``error`` is how a caller tells "Slack won't tell us" apart from "Slack told us
    and there's no email", which the link route needs to decide whether it can
    perform its identity check at all.

    Never raises: an identity-link attempt shouldn't fail because a Slack lookup
    hiccupped.
    """
    token = os.getenv("SLACK_BOT_TOKEN", "")
    if not token or not user_id:
        return {"display_name": None, "email": None, "error": "no_token"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://slack.com/api/users.info",
                headers={"Authorization": f"Bearer {token}"},
                params={"user": user_id},
            )
        body = resp.json()
    except Exception:  # noqa: BLE001 - best-effort lookup
        logger.warning("[slack] users.info failed for %s", user_id, exc_info=True)
        return {"display_name": None, "email": None, "error": "request_failed"}
    if not body.get("ok"):
        # missing_scope means users:read.email isn't granted — expected until the app
        # is reinstalled, so info rather than warning.
        logger.info("[slack] users.info -> %s", body.get("error"))
        return {"display_name": None, "email": None, "error": body.get("error")}
    user = body.get("user") or {}
    profile = user.get("profile") or {}
    handle = user.get("name")
    return {
        "display_name": f"@{handle}" if handle else profile.get("real_name"),
        "email": profile.get("email"),
        "error": None,
    }


# --------------------------------------------------------------------------- use case


class SlackGatewayUseCase:
    """v1 runs every Slack turn as one shared acting-user identity (the API key above);
    per-user verified linking replaces that later. No constructor deps — the ACP use
    case is built per-turn, bound to the resolved principal + delegation headers, in
    ``_dispatch``."""

    async def handle_slack_event(
        self,
        *,
        body: bytes,
        headers: dict[str, str],
        payload: dict[str, Any],
        background: BackgroundTasks,
    ) -> dict:
        # 1. URL-verification handshake (Slack pings the Request URL on save).
        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge")}

        # 2. Verify the signature against the app's signing secret (from the microservice).
        api_app_id = payload.get("api_app_id") or ""
        if _DEV_SKIP_VERIFY:
            logger.warning(
                "SLACK_GATEWAY_DEV_SKIP_VERIFY is ON — skipping signature verification. "
                "DEV ONLY; the gateway is unauthenticated in this mode."
            )
        else:
            signing_secret = await self._fetch_signing_secret(api_app_id)
            if not verify_signature(
                signing_secret,
                headers.get("x-slack-request-timestamp", ""),
                headers.get("x-slack-signature", ""),
                body,
            ):
                logger.warning(
                    "slack signature verification failed for app %s", api_app_id
                )
                return {"ok": False}  # 200 to Slack, but drop it

        inbound = normalize(payload)
        if inbound is None:
            return {"ok": True}  # event we don't act on

        # 3. Dedup: Slack redelivers at-least-once, so skip an event_id we've already
        #    seen — otherwise a retry starts a second turn for the same message.
        event_id = payload.get("event_id")
        if await self._already_processed(event_id):
            logger.info("[slack] duplicate event %s skipped", event_id)
            return {"ok": True}

        # 4. ACK fast (Slack's ~3s budget); run the turn out-of-band.
        background.add_task(self._run_turn, inbound)
        return {"ok": True}

    async def _already_processed(self, event_id: str | None) -> bool:
        """Dedup Slack's at-least-once HTTP delivery on the envelope ``event_id`` via a
        Redis ``SET NX`` with a short TTL. Returns True when the id was already seen
        (skip it). Fail-open (False) with no id / no Redis / any Redis error, so dedup
        can never drop a legitimate first delivery."""
        if not event_id:
            return False
        try:
            pool = GlobalDependencies().redis_pool
        except Exception:  # noqa: BLE001 - deps not initialized (unit test) -> allow
            return False
        if pool is None:
            return False
        try:
            import redis.asyncio as redis

            client = redis.Redis(connection_pool=pool)
            first_time = await client.set(
                f"slack:dedup:{event_id}", "1", nx=True, ex=_EVENT_DEDUP_TTL_SECONDS
            )
            return not first_time
        except Exception:  # noqa: BLE001 - dedup is best-effort; never block a turn
            logger.warning(
                "[slack] event dedup check failed; processing anyway", exc_info=True
            )
            return False

    async def handle_slash_command(
        self, *, body: bytes, headers: dict[str, str], form: dict[str, Any]
    ) -> dict:
        """Handle a Slack slash command (form-encoded). Returns the response body
        Slack renders (ephemeral). Verifies the signature like events (skipped in
        dev). v1 supports ``/agents`` — list the agents invocable via ``@agent
        <name>``. Synchronous: the registry read is a cheap DB query, well within
        Slack's 3s budget, so no response_url round-trip is needed."""
        if _DEV_SKIP_VERIFY:
            logger.warning(
                "SLACK_GATEWAY_DEV_SKIP_VERIFY is ON — skipping slash-command signature "
                "verification. DEV ONLY."
            )
        else:
            api_app_id = form.get("api_app_id") or ""
            signing_secret = await self._fetch_signing_secret(api_app_id)
            if not verify_signature(
                signing_secret,
                headers.get("x-slack-request-timestamp", ""),
                headers.get("x-slack-signature", ""),
                body,
            ):
                logger.warning(
                    "slack slash-command signature failed for app %s", api_app_id
                )
                return {
                    "response_type": "ephemeral",
                    "text": "Signature verification failed.",
                }

        command = (form.get("command") or "").strip()
        if command == "/agents":
            # Open the picker modal; fall back to the plain ephemeral list when we
            # can't (no trigger_id, no agents, or views.open failed).
            trigger_id = form.get("trigger_id") or ""
            channel_id = form.get("channel_id") or ""
            if trigger_id and await self._open_agents_modal(trigger_id, channel_id):
                return {}  # empty 200: Slack shows nothing; the modal is already open
            return _agents_list_response(await self._list_agents())
        return {
            "response_type": "ephemeral",
            "text": f"Unsupported command: {command or '(none)'}",
        }

    async def handle_interaction(
        self,
        *,
        body: bytes,
        headers: dict[str, str],
        form: dict[str, Any],
        background: BackgroundTasks,
    ) -> dict:
        """Handle a Slack interactivity POST. v1 handles the /agents modal's
        ``view_submission`` (see _submit_agents_modal). Payload is form-encoded with a
        JSON ``payload`` field; the signature covers the raw body (verified like slash
        commands)."""
        try:
            payload = json.loads(form.get("payload") or "{}")
        except (TypeError, ValueError):
            return {}

        if _DEV_SKIP_VERIFY:
            logger.warning(
                "SLACK_GATEWAY_DEV_SKIP_VERIFY is ON — skipping interaction signature "
                "verification. DEV ONLY."
            )
        else:
            api_app_id = payload.get("api_app_id") or ""
            signing_secret = await self._fetch_signing_secret(api_app_id)
            if not verify_signature(
                signing_secret,
                headers.get("x-slack-request-timestamp", ""),
                headers.get("x-slack-signature", ""),
                body,
            ):
                logger.warning(
                    "slack interaction signature failed for app %s", api_app_id
                )
                return {}

        if payload.get("type") != "view_submission":
            return {}
        view = payload.get("view") or {}
        if view.get("callback_id") == _AGENTS_MODAL_CALLBACK:
            return await self._submit_agents_modal(payload, view, background)
        return {}  # not ours — ack empty

    async def _submit_agents_modal(
        self, payload: dict, view: dict, background: BackgroundTasks
    ) -> dict:
        """/agents modal submission: post a breadcrumb (records the request + anchors
        the reply thread) then build the SAME InboundSlack an @mention would and run
        the turn out-of-band."""
        values = (view.get("state") or {}).get("values") or {}
        agent_sel = (values.get("agent_block") or {}).get("agent_select") or {}
        agent = (agent_sel.get("selected_option") or {}).get("value") or ""
        message = ((values.get("message_block") or {}).get("message_input") or {}).get(
            "value"
        ) or ""
        channel = view.get("private_metadata") or ""
        user = (payload.get("user") or {}).get("id") or ""
        team = (payload.get("team") or {}).get("id") or ""

        if not (agent and message and channel):
            return {
                "response_action": "errors",
                "errors": {"message_block": "Pick an agent and enter a message."},
            }

        # Breadcrumb: reads like the equivalent @mention, records who asked, and its ts
        # anchors the reply thread. Posted by the bot, so normalize() ignores it (no
        # second turn). If the bot isn't in the channel the post fails — the modal can
        # be launched from anywhere, but we can only post where the bot is a member.
        command = f"@agentex {agent} {message}"
        crumb = await self._slack_api(
            "chat.postMessage",
            {
                "channel": channel,
                "text": command,  # notification / accessibility fallback
                "blocks": [
                    {"type": "section", "text": {"type": "mrkdwn", "text": command}},
                    # Attribution as a context block — Slack renders it as a small,
                    # muted footer rather than inline body text.
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"via <@{user}> through *{agent}*",
                            }
                        ],
                    },
                ],
            },
        )
        if not crumb.get("ok"):
            logger.warning("[slack] breadcrumb post failed: %s", crumb.get("error"))
            return {
                "response_action": "errors",
                "errors": {
                    "message_block": "I couldn't post in that channel — invite me to "
                    "it (`/invite`), then try again."
                },
            }

        inbound = InboundSlack(
            team_id=team,
            channel=channel,
            user=user,
            text=f"{agent} {message}",  # mirrors an @mention so _resolve_target matches
            thread_ts=crumb.get("ts") or "",
            selector=agent,
        )
        background.add_task(self._run_turn, inbound)
        return {}  # empty 200 closes the modal

    async def _run_turn(self, inbound: InboundSlack) -> None:
        try:
            # Whose identity runs this turn.
            #
            # If the invoking Slack user has an active link with a usable stored
            # credential, the turn runs as THEM: their principal for authz/ownership,
            # and their SGP API key on the delegation headers. That key is what
            # becomes x-acting-user-api-key on the ACP call, which is what makes the
            # agent's user-scoped tools (Notion, Linear, the hosted Slack MCP) resolve
            # that person's own connections instead of a shared account's.
            #
            # Otherwise we fall back to the shared gateway bot — unchanged behavior,
            # so an unlinked user still gets a working turn, just without their
            # personal integrations. Prompting them to link is a separate concern.
            principal, auth_headers, sgp_user_id = await self._turn_identity(inbound)

            if sgp_user_id is None:
                # Not running as a person: either unlinked, or linked with a
                # credential we can't use (expired session, undecryptable). Offer the
                # link either way — a dead credential needs the same fix as no
                # credential. Rate-limited and best-effort; it never affects the turn,
                # which continues as the bot below (or is refused just after).
                await self._offer_link(inbound)

            if principal is None and auth_headers is None:
                # Only reachable when linking is mandatory and this user hasn't.
                await self._deliver(inbound, _UNLINKED_MESSAGE)
                return

            target, prompt = await self._resolve_target(inbound, auth_headers)

            if not await self._authorize(target):
                await self._deliver(
                    inbound, f"You're not authorized to run {target.label()}."
                )
                return

            # golden-agent is the only agent with Slack WRITE tools (SlackBot is
            # auto-enabled on every slack-origin golden-agent turn, config or not), so it
            # posts its own reply into the thread. For it we DON'T relay (that would
            # double-post the answer). We DO still show "thinking…" while it works — that
            # clears on its own when the agent posts its reply (posting a message clears
            # the assistant status), so the agent's post IS the done signal. Every other
            # agent — registered agents (their own name, no config) and SYNC agents — has
            # no Slack tools, so the gateway is the single writer and relays. Errors still
            # surface via except. (config_id can't distinguish this: configs are personas
            # that KEEP the golden-agent name, so the name is the exact self-posting
            # signal.)
            if target.agent_name == _DEFAULT_AGENT_NAME:
                await self._set_status(inbound, "is thinking…")
                await self._dispatch(
                    target,
                    inbound,
                    prompt,
                    principal,
                    auth_headers,
                    collect=False,
                    sgp_user_id=sgp_user_id,
                )
                return

            # AI-app "thinking…" indicator while the turn runs (assistant pane); cleared
            # automatically when we post the reply. No-op outside an assistant thread.
            await self._set_status(inbound, "is thinking…")
            reply = await self._dispatch(
                target,
                inbound,
                prompt,
                principal,
                auth_headers,
                sgp_user_id=sgp_user_id,
            )
            note = f"_via {target.label()}_"  # attribution
            await self._deliver(
                inbound,
                f"{reply}\n\n{note}"
                if reply
                else f"_(no reply from {target.label()})_",
            )
        except Exception:
            logger.exception("slack gateway turn failed")
            await self._deliver(
                inbound, "Something went wrong handling that. Please retry."
            )

    async def _turn_identity(
        self, inbound: InboundSlack
    ) -> tuple[Any, dict[str, str] | None, str | None]:
        """Decide whose identity this turn runs as.

        Returns ``(principal, auth_headers, sgp_user_id)``:

        - linked user with a usable credential -> their principal, their delegation
          headers, their SGP user id. The turn acts as them end to end.
        - otherwise -> the shared bot's principal and headers, and ``None`` for the
          user id (which keeps the legacy thread-wide task key, so nothing that's
          already running gets orphaned).
        - ``(None, None, None)`` only when ``_REQUIRE_LINKED_USER`` is set and this
          user has no usable link, telling the caller to refuse the turn.

        A resolution *failure* propagates rather than falling back: silently running
        as the bot because the database hiccuped would be indistinguishable from
        "this person isn't linked", and the two need different handling.
        """
        identity = await self._resolve_invoking_identity(inbound)
        if identity is not None:
            headers = await self._identity_link_service().acting_headers(identity)
            if headers is not None:
                logger.info(
                    "[slack] turn acting as sgp user %s (linked from %s)",
                    identity.sgp_user_id,
                    inbound.user,
                )
                return identity.principal, headers, identity.sgp_user_id
            # Linked but unusable — no stored key, expired, or undecryptable. The
            # service has already logged which. Treated the same as unlinked here;
            # re-link prompting is handled separately.

        if _REQUIRE_LINKED_USER:
            logger.info(
                "[slack] refusing turn: user %s in team %s has no usable link",
                inbound.user,
                inbound.team_id,
            )
            return None, None, None

        bot_principal, bot_headers = await self._acting_identity()
        logger.info(
            "[slack] turn falling back to the shared bot identity for user %s",
            inbound.user,
        )
        return bot_principal, bot_headers, None

    def _identity_link_service(self):
        """Build the identity-link service.

        Constructed inline for the same reason as ``_get_agent_by_name``: this use
        case is instantiated per-request with no constructor deps, and the identity
        map is infrastructure the gateway owns rather than something a caller passes
        in.
        """
        # Local imports keep these off the module-load path.
        from src.domain.repositories.identity_link_repository import (
            IdentityLinkRepository,
        )
        from src.domain.services.identity_link_service import IdentityLinkService

        engine = database_async_read_write_engine()
        return IdentityLinkService(
            IdentityLinkRepository(
                database_async_read_write_session_maker(engine),
                database_async_read_only_session_maker(engine),
            )
        )

    async def _resolve_invoking_identity(self, inbound: InboundSlack):
        """Resolve the Slack user who triggered this turn to an SGP identity, or
        None when they have no active link."""
        from src.domain.entities.identity_links import IdentityProvider

        return await self._identity_link_service().resolve(
            provider=IdentityProvider.SLACK,
            external_team_id=inbound.team_id,
            external_user_id=inbound.user,
        )

    def _task_name(self, inbound: InboundSlack, sgp_user_id: str | None) -> str:
        """The conversation key.

        For a linked user the task is per (workspace, channel, thread, user): each
        invoker gets their own task, in their own account, holding only their own
        turns. That's what makes per-user ownership coherent in a shared thread — one
        task can't be owned by two people — and it removes the reply-attribution
        race, since a task now only ever contains one user's messages.

        The agent loses the other participants' turns from its own history by design;
        it recovers that context by reading the thread with its Slack tools (the
        ``[Slack context]`` prefix carries the channel and thread for exactly that).

        **Team and channel are in the key deliberately.** ``task/create`` is
        get-or-create on the name, so two turns that produce the same name become one
        task — mixing their prompts, metadata, agent config and account context into
        a single conversation. ``thread_ts`` alone does not rule that out: it is
        unique within a workspace but nothing makes it unique *across* workspaces,
        and this gateway is multi-workspace (``team_id`` is part of the identity
        everywhere else). The odds of two workspaces minting the same microsecond
        timestamp are tiny, but the failure is silent and cross-tenant, and the two
        extra segments cost nothing.

        They also bound the damage if ``thread_ts`` is ever empty — ``normalize()``
        falls back to ``""`` when an event carries neither ``thread_ts`` nor ``ts``.
        With team and channel present that degrades to one task per (workspace,
        channel, user), which is a reasonable conversation anyway; on the old key it
        would have collapsed every such turn into a single global task.

        Unlinked users keep the legacy thread-wide key, so turning this on doesn't
        orphan conversations already in flight. That key has the same cross-workspace
        weakness and predates this change; widening it would re-key live threads, so
        it's left alone here.
        """
        if sgp_user_id:
            return (
                f"slack:{inbound.team_id}:{inbound.channel}:"
                f"{inbound.thread_ts}:{sgp_user_id}"
            )
        return f"slack:{inbound.thread_ts}"

    async def _resolve_config_id(
        self, name: str, auth_headers: dict[str, str]
    ) -> str | None:
        """Resolve an agent_config NAME -> id via SGP's directory
        (GET {SGP}/v5/agent_configs?name=), authenticated with whatever credential the
        acting identity carries. Cached by (account, name) for the process lifetime.
        Fail-safe -> None (no SGP base / no credential / any error) so the caller
        falls back to the fixed default id.

        The credential check is deliberately *form-agnostic*. It used to require
        ``x-api-key``, which the shared bot has but a linked user does not: a linked
        user's acting headers carry their session cookie instead. That mismatch made
        this silently return None for exactly the users this feature is for, so they
        would land on the default config while a bot-run turn resolved the name
        correctly — a difference in agent behavior with nothing in the logs pointing
        at the cause. Forward whatever we hold and let the directory decide.

        Unverified: whether that endpoint accepts cookie auth. If it doesn't, the
        request fails and we fall back to the default id, which is the same outcome
        as before this change — so this is safe either way, just no longer silently
        wrong for api-key callers only. It could not be checked because
        ``SLACK_GATEWAY_SGP_BASE_URL`` is unset in dev, which also means this whole
        path is inert there today.
        """
        has_credential = any(
            auth_headers.get(h) for h in ("x-api-key", "cookie", "authorization")
        )
        if not (_SGP_BASE_URL and name and has_credential):
            return None
        cache_key = (auth_headers.get("x-selected-account-id", ""), name)
        if cache_key in _CONFIG_ID_CACHE:
            return _CONFIG_ID_CACHE[cache_key]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{_SGP_BASE_URL}/v5/agent_configs",
                    headers=auth_headers,
                    params={"name": name},
                )
            items = (resp.json() or {}).get("items") or []
            for cfg in items:
                if cfg.get("name") == name and cfg.get("id"):
                    _CONFIG_ID_CACHE[cache_key] = cfg["id"]
                    return cfg["id"]
            logger.warning("[slack] no agent_config named %r in SGP", name)
        except Exception:  # noqa: BLE001 - best-effort; fall back to the default id
            logger.warning(
                "[slack] config-id resolution failed for %r", name, exc_info=True
            )
        return None

    async def _message_send_with_race_retry(self, acp, params, agent_id):
        """Send a SYNC agent's ``message/send`` (which get-or-creates the thread task and
        returns the reply), retrying the whole call on the create-race.

        Two concurrent first messages for the same thread both miss the get-or-create
        lookup and race the insert on the globally-unique task name; the loser raises
        ``DuplicateItemError``. Retrying re-runs get-or-create — but the lookup reads the
        (possibly-lagging) read replica, so a single retry can still miss the winner's
        task and race the create again. Loop with a short backoff so replication catches
        up; give up only after ``_CREATE_RACE_ATTEMPTS`` (persistent lag → surfaced to
        the caller). Each raising attempt fails on the insert before appending anything,
        so retries never duplicate the turn's message."""
        last: DuplicateItemError | None = None
        for attempt in range(_CREATE_RACE_ATTEMPTS):
            try:
                return await acp.handle_rpc_request(
                    method=AgentRPCMethod.MESSAGE_SEND, params=params, agent_id=agent_id
                )
            except DuplicateItemError as exc:
                last = exc
                if attempt < _CREATE_RACE_ATTEMPTS - 1:
                    await asyncio.sleep(_CREATE_RACE_BACKOFF_S)
        raise last  # exhausted retries — let _run_turn surface the failure

    async def _resolve_task_after_race(self, task_service, task_name: str):
        """Resolve the winner's task by name after an async-path create-race
        (DuplicateItemError). The lookup reads the (possibly-lagging) read replica, so
        retry on ItemDoesNotExist with a short backoff until replication catches up —
        the task exists on the primary, the replica just hasn't seen it yet. Give up
        after ``_CREATE_RACE_ATTEMPTS`` (persistent lag → surfaced to the caller)."""
        last: ItemDoesNotExist | None = None
        for attempt in range(_CREATE_RACE_ATTEMPTS):
            try:
                return await task_service.get_task(name=task_name)
            except ItemDoesNotExist as exc:
                last = exc
                if attempt < _CREATE_RACE_ATTEMPTS - 1:
                    await asyncio.sleep(_CREATE_RACE_BACKOFF_S)
        raise last

    async def _dispatch(
        self,
        target: Target,
        inbound: InboundSlack,
        prompt: str,
        principal: Any,
        auth_headers: dict[str, str],
        *,
        collect: bool = True,
        sgp_user_id: str | None = None,
    ) -> str | None:
        """Create-or-resume a task on the resolved agent, then inject the turn, acting as
        the shared v1 identity (x-api-key -> principal for authz, delegated downstream as
        x-acting-user-api-key so tools act as that user). The principal + headers are
        resolved once per turn in ``_run_turn`` and passed in.

        The task is keyed on the Slack thread (``slack:{thread_ts}``), so a thread is one
        conversation. ASYNC/AGENTIC agents (e.g. golden-agent) get a long-lived workflow:
        TASK_CREATE on the FIRST turn (re-creating a running workflow raises
        WorkflowAlreadyStarted), then event/send + poll for the reply. SYNC agents have
        no event stream — a single message/send get-or-creates the task and returns the
        reply synchronously.
        """
        # Local import avoids a domain -> temporal import cycle at module load.
        from src.temporal.scheduled_agent_run_factory import (
            build_acp_use_case_for_principal,
        )

        acp = build_acp_use_case_for_principal(
            GlobalDependencies(), principal, request_headers=auth_headers
        )
        agent = await acp.agent_repository.get(name=target.agent_name)
        task_name = self._task_name(inbound, sgp_user_id)
        # golden-agent isn't relayed (it self-posts), so its context gets the directive to
        # post its own reply. Keyed on the same signal _run_turn uses to skip the relay.
        content = TextContentEntity(
            author=MessageAuthor.USER,
            content=_turn_content(
                inbound, prompt, self_posts=target.agent_name == _DEFAULT_AGENT_NAME
            ),
            format=TextFormat.MARKDOWN,
        )
        # First-turn task params: golden-agent's agent_config id (when this turn resolved
        # to one) + any gateway-default MCPs. A routed non-golden agent carries no
        # config_id and ignores params it doesn't use.
        create_params: dict[str, Any] = {}
        if target.config_id:
            create_params["config_id"] = target.config_id
        if _DEFAULT_MCPS:
            create_params["mcps"] = _DEFAULT_MCPS

        # SYNC agents have no event stream: one message/send get-or-creates the task and
        # returns the reply synchronously. (event/send is async/agentic-only, which is
        # why routing to a SYNC agent otherwise fails with "Unsupported method".)
        if agent.acp_type == ACPType.SYNC:
            send = SendMessageRequestEntity(
                task_name=task_name,
                content=content,
                task_params=create_params,
                stream=False,
            )
            replies = await self._message_send_with_race_retry(acp, send, agent.id)
            return _agent_text(replies or [])

        # ASYNC / AGENTIC: TASK_CREATE only on the first turn, then event/send + poll.
        task = await self._existing_task(acp.task_service, task_name)
        if task is None:
            task_metadata = {
                "channel": "slack",
                "sender_id": target.label(),
                "thread_ts": inbound.thread_ts,
                "channel_id": inbound.channel,
                # Who actually asked. The Slack id is what the agent's Slack tools
                # act on; the SGP id (present only for a linked user) is what makes
                # the task attributable to a human rather than to the gateway bot.
                "slack_user_id": inbound.user,
            }
            if sgp_user_id:
                task_metadata["sgp_user_id"] = sgp_user_id
            if target.config_id:
                task_metadata["config_id"] = target.config_id
            try:
                task = await acp.handle_rpc_request(
                    method=AgentRPCMethod.TASK_CREATE,
                    params=CreateTaskRequestEntity(
                        name=task_name,
                        params=create_params,
                        task_metadata=task_metadata,
                    ),
                    agent_id=agent.id,
                )
            except DuplicateItemError:
                # A concurrent first event for the same thread won the create race
                # (task_name is globally unique, and the DB insert fails before any
                # workflow starts). Resolve the winner's task and just send this turn's
                # event, as a follow-up would. Retry the lookup: it reads the (possibly
                # lagging) replica, which may not have the just-created task yet.
                task = await self._resolve_task_after_race(acp.task_service, task_name)

        # Snapshot existing messages so we can isolate THIS turn's reply (only needed
        # when we're going to collect + relay it).
        seen = (
            await self._seen_message_ids(acp.task_message_service, task.id)
            if collect
            else set()
        )
        await acp.handle_rpc_request(
            method=AgentRPCMethod.EVENT_SEND,
            params=SendEventRequestEntity(task_name=task_name, content=content),
            agent_id=agent.id,
        )
        # Self-posting agents (golden-agent) own their Slack output: send the event and
        # return without polling — the gateway never relays their reply.
        if not collect:
            return None
        # Poll the task's messages for this turn's settled agent reply.
        return await self._collect_reply(acp.task_message_service, task.id, seen)

    async def _existing_task(self, task_service, name: str):
        """Return the task with this name if it already exists, else None. Lets a
        same-thread follow-up skip TASK_CREATE (which would re-start the running workflow
        -> WorkflowAlreadyStarted) and just send the next event."""
        try:
            return await task_service.get_task(name=name)
        except ItemDoesNotExist:
            return None

    async def _recent_messages(self, msg_service, task_id: str) -> list:
        """The newest page of task messages, returned in chronological (ascending)
        order. Fetches DESC so the most recent messages are always in the window even
        on a long-running task (>_MESSAGE_PAGE messages) — a plain ascending page 1
        would return the OLDEST messages and never see this turn's reply — then
        reverses to chronological so a multi-part reply joins in order."""
        msgs = await msg_service.get_messages(
            task_id=task_id, limit=_MESSAGE_PAGE, page_number=1, order_direction="desc"
        )
        return list(reversed(msgs or []))

    async def _seen_message_ids(self, msg_service, task_id: str) -> set[str]:
        msgs = await self._recent_messages(msg_service, task_id)
        return {m.id for m in msgs if getattr(m, "id", None)}

    async def _collect_reply(
        self,
        msg_service,
        task_id: str,
        seen: set[str],
        *,
        timeout_s: float = 120.0,
        interval_s: float = 2.0,
        quiescence_s: float = 6.0,
    ) -> str | None:
        """Poll for THIS turn's reply: new agent-authored text that settles (unchanged
        for quiescence_s) or times out. Filters on ids not present before the event so a
        reused task's prior reply isn't returned. (Interim — prefer the stream later.)"""
        waited, last, stable = 0.0, None, 0.0
        while waited < timeout_s:
            await asyncio.sleep(interval_s)
            waited += interval_s
            msgs = await self._recent_messages(msg_service, task_id)
            new = [m for m in msgs if getattr(m, "id", None) not in seen]
            text = _agent_text(new)
            if text and text == last:
                stable += interval_s
                if stable >= quiescence_s:
                    return text
            elif text:
                last, stable = text, 0.0
        return last

    async def _acting_identity(self) -> tuple[Any, dict[str, str]]:
        """The gateway's bot identity. The bot API key + account come from env /
        k8s-secret. Verify the key -> principal (for authz), and return the credential
        headers (delegated to the agent, where x-api-key becomes x-acting-user-api-key).
        Auth needs BOTH x-api-key and x-selected-account-id — the key alone 401s.

        Missing bot key: FAIL CLOSED when authz is enabled (AGENTEX_AUTH_URL set), so a
        misconfigured deploy never dispatches unauthenticated (which would run with no
        principal, bypassing the per-turn authz boundary). Only the authz-off local case
        (no AGENTEX_AUTH_URL) is allowed to run with no principal — the dev bypass."""
        api_key = _ACTING_BOT_API_KEY
        if not api_key:
            if os.getenv("AGENTEX_AUTH_URL"):
                raise RuntimeError(
                    "SLACK_GATEWAY_ACTING_BOT_API_KEY is unset while authz is enabled "
                    "(AGENTEX_AUTH_URL); refusing to dispatch a Slack turn without a bot "
                    "principal."
                )
            return None, {}  # authz off (local dev) — run with no principal
        account_id = _ACTING_ACCOUNT_ID
        # Local imports avoid an import cycle at module load.
        from src.adapters.authentication.adapter_agentex_authn_proxy import (
            AgentexAuthenticationProxy,
        )
        from src.config.dependencies import resolve_environment_variable_dependency
        from src.config.environment_variables import EnvVarKeys

        headers = {"x-api-key": api_key}
        if account_id:
            headers["x-selected-account-id"] = account_id
        authn = AgentexAuthenticationProxy(
            agentex_auth_url=resolve_environment_variable_dependency(
                EnvVarKeys.AGENTEX_AUTH_URL
            ),
            environment=resolve_environment_variable_dependency(EnvVarKeys.ENVIRONMENT),
        )
        principal = await authn.verify_headers(headers)
        return principal, headers

    async def _fetch_signing_secret(self, api_app_id: str) -> str:
        # Signing secret from env / k8s-secret. Empty => verify_signature fails closed.
        # api_app_id is unused (one shared app) but kept on the interface.
        return os.getenv("SLACK_SIGNING_SECRET", "")

    async def _resolve_account(self, team_id: str) -> str:
        # TODO: Slack team_id -> SGP account (tenant-aware from day one). v1 derives the
        # account from the acting-user key's principal, so this is unused for now.
        return ""

    async def _resolve_target(
        self, inbound: InboundSlack, auth_headers: dict[str, str]
    ) -> tuple[Target, str]:
        """Resolution cascade for the ``@agent <selector>`` token:
        1. an SGP agent_config with that name -> golden-agent + that config_id;
        2. a registered agentex agent with that name -> route to that runtime;
        3. neither (or no selector) -> golden-agent + the default config_id.
        The selector is stripped from the prompt only when it matched (1 or 2); an
        unmatched first word is just part of the message.
        """
        selector = inbound.selector
        if selector:
            config_id = await self._resolve_config_id(selector, auth_headers)
            if config_id:
                return (
                    Target(_DEFAULT_AGENT_NAME, config_id=config_id),
                    _strip_selector(inbound.text, selector),
                )
            if await self._get_agent_by_name(selector) is not None:
                return (
                    Target(agent_name=selector),
                    _strip_selector(inbound.text, selector),
                )
        return (
            Target(_DEFAULT_AGENT_NAME, config_id=_DEFAULT_CONFIG_ID or None),
            inbound.text,
        )

    async def _get_agent_by_name(self, name: str):
        """The runtime-registry tier: does an agent with this name exist? Read-only repo
        query — the directory is infrastructure, so it needs NO credential (that's why we
        don't go through the authenticated API here). A selector that names a real agent
        routes there instead of golden-agent.

        Access control is NOT enforced here — it's enforced at dispatch, where
        ``build_acp_use_case_for_principal`` runs the agent.execute check against the
        acting principal. v1 that's the shared identity; once verified Slack->SGP linking
        lands, it becomes the invoking user's (credential-free) principal, so a user can
        only actually run agents they're permitted to — no API key required for either
        the lookup or the authz."""
        engine = database_async_read_write_engine()
        repo = AgentRepository(
            database_async_read_write_session_maker(engine),
            database_async_read_only_session_maker(engine),
        )
        try:
            return await repo.get(name=name)
        except ItemDoesNotExist:
            return None

    async def _list_agents(self):
        """Credential-free registry read (same rationale as _get_agent_by_name — the
        directory is infrastructure, no API key needed). Returns READY agents sorted
        by name: the ones actually invocable via @mention."""
        engine = database_async_read_write_engine()
        repo = AgentRepository(
            database_async_read_write_session_maker(engine),
            database_async_read_only_session_maker(engine),
        )
        agents = await repo.list(limit=100)
        ready = [a for a in agents if getattr(a, "status", None) == AgentStatus.READY]
        return sorted(ready, key=lambda a: a.name)

    async def _authorize(self, target: Target) -> bool:
        # v1: no extra gate here — the acting-user identity's own grants are still
        # enforced by the ACP use case's internal authz (agent.execute / task.*).
        # TODO: explicit EXECUTE-on-target check once per-user linking lands.
        return True

    async def _fetch_bot_token(self) -> str:
        # Bot token from env / k8s-secret.
        return os.getenv("SLACK_BOT_TOKEN", "")

    async def _offer_link(self, inbound: InboundSlack) -> bool:
        """DM the invoking user a one-time link to connect their SGP account.

        Returns True only when a DM actually went out. Entirely best-effort: this runs
        alongside a turn that is already proceeding (as the shared bot, or being
        refused), and no failure here may change that outcome.

        **The link is DMed, never posted in channel.** The nonce is a bearer token —
        whoever holds it gets linked to this Slack identity by signing in as
        themselves. In a channel, the first person to click it would bind *this*
        user's Slack identity to *their own* SGP account. So if the DM can't be sent
        we say so and stop, rather than falling back to somewhere visible.

        Rate limiting is two-layer and deliberately so: ``claim_send`` caps DMs about
        one live link (default 2, so a re-mention re-sends rather than going quiet),
        and a cooldown key stops a fresh nonce from re-arming that budget on every
        mention once the old one expires.
        """
        if not _PUBLIC_BASE_URL:
            logger.info(
                "[slack] link offer skipped: SLACK_GATEWAY_PUBLIC_BASE_URL is unset"
            )
            return False

        from src.domain.services.link_nonce_service import LinkNonceService, LinkRequest

        if not await self._claim_offer_cooldown(inbound):
            logger.info(
                "[slack] link offer suppressed by cooldown for %s", inbound.user
            )
            return False

        profile = await slack_user_profile(inbound.user)
        request = LinkRequest(
            provider="slack",
            external_team_id=inbound.team_id,
            external_user_id=inbound.user,
            display_name=profile.get("display_name") or inbound.user,
            # Stored so a later change can answer the original question; nothing
            # replays it yet.
            pending_turn={
                "text": inbound.text,
                "channel": inbound.channel,
                "thread_ts": inbound.thread_ts,
            },
        )

        service = LinkNonceService()
        try:
            token, reused = await service.create_or_reuse(request)
            allowed = await service.claim_send(request)
        except Exception:  # noqa: BLE001 - Redis down: no offer, turn unaffected
            logger.warning("[slack] link offer failed to mint a nonce", exc_info=True)
            return False

        # Opened before the send-cap check because BOTH branches need the channel id
        # to build the deep link below — telling someone to "check your DMs" without
        # taking them there is the failure this method exists to avoid. Idempotent:
        # conversations.open returns the existing DM rather than creating another.
        opened = await self._slack_api("conversations.open", {"users": inbound.user})
        dm_channel = (
            (opened.get("channel") or {}).get("id") if opened.get("ok") else None
        )
        if not dm_channel:
            logger.warning(
                "[slack] conversations.open failed for %s: %s",
                inbound.user,
                opened.get("error"),
            )
            return False

        # Slack files bot conversations under "Apps", NOT in the Direct messages
        # list, so a person told to check their DMs looks in the one place the
        # message isn't. Observed in the field: the first real offer was delivered
        # correctly, confirmed present via conversations.history, and still reported
        # as never received. app_redirect works on web and desktop, unlike a
        # slack:// URI.
        dm_deeplink = f"https://slack.com/app_redirect?channel={dm_channel}&team={inbound.team_id}"
        url = f"{_PUBLIC_BASE_URL}/integrations/slack/link?nonce={token}"

        # The connect link goes in the ephemeral as well as the DM. An ephemeral is
        # single-viewer — Slack renders it for one user, keeps it out of channel
        # history and out of search — so it has exactly the same audience as the DM,
        # and putting the link there costs a round trip through a conversation people
        # cannot find. The DM stays because ephemerals are transient: reload Slack
        # before clicking and it's gone, and the offer cooldown would then block a
        # retry for an hour.
        #
        # This is NOT licence to put the link in an ordinary channel message. The
        # nonce is a bearer token; the first reader of a broadcast could bind this
        # user's Slack identity to their own SGP account. Single-viewer is the
        # property that makes the ephemeral safe, not "it's in the channel anyway".
        if not allowed:
            # Past the DM cap — but an ephemeral costs nothing and is what the user
            # is actually looking at, so still hand them the live link.
            await self._post_ephemeral(
                inbound,
                f"<{url}|Connect your SGP account> to let me use your own tools "
                f"when you ask me things here.\n"
                f"_Only you can see this. The same link is in "
                f"<{dm_deeplink}|our DM>._",
            )
            return False
        posted = await self._slack_api(
            "chat.postMessage",
            {
                "channel": dm_channel,
                "unfurl_links": False,
                "text": (
                    "Connect your SGP account and I'll use *your* tools "
                    "(Notion, Linear, …) when you ask me things in Slack.\n\n"
                    f"<{url}|Connect my account>\n\n"
                    "This link is just for you and expires in a few minutes. "
                    "Don't forward it — anyone who opens it could connect your "
                    "Slack identity to their own SGP account."
                ),
            },
        )
        if not posted.get("ok"):
            logger.warning(
                "[slack] link DM failed for %s: %s", inbound.user, posted.get("error")
            )
            return False

        logger.info(
            "[slack] link offer DMed to %s (nonce %s)",
            inbound.user,
            "reused" if reused else "new",
        )
        await self._post_ephemeral(
            inbound,
            f"<{url}|Connect your SGP account> and I'll use your own tools "
            f"(Notion, Linear, …) when you ask me things here.\n"
            f"_Only you can see this message. I've also sent the link to "
            f"<{dm_deeplink}|our DM>, in case this one disappears._",
        )
        return True

    async def _claim_offer_cooldown(self, inbound: InboundSlack) -> bool:
        """True if we may offer this user a link now, and records the offer.

        Fails *open* on a Redis problem: the alternative is never offering, and the
        per-link ``claim_send`` cap still bounds the damage.
        """
        key = f"slack:link_offer:{inbound.team_id}:{inbound.user}"
        try:
            pool = GlobalDependencies().redis_pool
            if pool is None:
                return True
            import redis.asyncio as redis

            client = redis.Redis(connection_pool=pool)
            # SET NX: only the first caller in the window wins.
            return bool(await client.set(key, "1", nx=True, ex=_LINK_OFFER_COOLDOWN_S))
        except Exception:  # noqa: BLE001 - see docstring
            logger.warning("[slack] link offer cooldown check failed", exc_info=True)
            return True

    async def _post_ephemeral(self, inbound: InboundSlack, text: str) -> None:
        """Post a message only the invoking user sees. Best-effort.

        Ephemeral so a channel isn't cluttered with onboarding nudges aimed at one
        person — and Slack rejects it outside a channel context (e.g. an assistant
        pane), which we swallow.
        """
        body = await self._slack_api(
            "chat.postEphemeral",
            {
                "channel": inbound.channel,
                "user": inbound.user,
                "thread_ts": inbound.thread_ts,
                "text": text,
            },
        )
        if not body.get("ok"):
            logger.info("[slack] postEphemeral -> %s", body.get("error"))

    async def _set_status(self, inbound: InboundSlack, status: str) -> None:
        """AI-app 'thinking…' indicator (assistant.threads.setStatus). Shows in the
        assistant pane while the turn runs; cleared when the reply is posted. Best-effort:
        no-op without a bot token, and Slack rejects it outside an assistant thread
        (e.g. a plain channel @mention) — we swallow that so it never breaks a turn."""
        token = await self._fetch_bot_token()
        if not token:
            logger.info("[slack] setStatus skipped: no bot token")
            return
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://slack.com/api/assistant.threads.setStatus",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "channel_id": inbound.channel,
                        "thread_ts": inbound.thread_ts,
                        "status": status,
                    },
                )
            body = resp.json()
            if body.get("ok"):
                logger.info(
                    "[slack] setStatus -> %s#%s", inbound.channel, inbound.thread_ts
                )
            else:
                # e.g. missing_scope (needs assistant:write) or not an assistant thread
                # (a plain channel @mention) — logged, never fatal to the turn.
                logger.warning("[slack] setStatus skipped: %s", body.get("error"))
        except Exception:
            logger.warning("setStatus request failed", exc_info=True)

    async def _deliver(self, inbound: InboundSlack, text: str) -> None:
        """Post the reply into the Slack thread with the bot token."""
        token = await self._fetch_bot_token()
        if not token:
            logger.info(
                "[slack] no bot token — would deliver -> %s#%s: %s",
                inbound.channel,
                inbound.thread_ts,
                text[:200],
            )
            return
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "channel": inbound.channel,
                    "thread_ts": inbound.thread_ts,
                    "text": text,
                },
            )
        body = resp.json()
        if body.get("ok"):
            logger.info(
                "[slack] delivered -> %s#%s: %s",
                inbound.channel,
                inbound.thread_ts,
                text[:200],
            )
        else:
            logger.warning("[slack] chat.postMessage failed: %s", body.get("error"))

    async def _slack_api(self, method: str, payload: dict) -> dict:
        """POST to the Slack Web API with the bot token; returns the parsed body.
        Returns ``{"ok": False, ...}`` (never raises) when the token is unset or the
        request fails, so callers can branch on ``ok`` uniformly."""
        token = await self._fetch_bot_token()
        if not token:
            logger.info("[slack] %s skipped: no bot token", method)
            return {"ok": False, "error": "no_bot_token"}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"https://slack.com/api/{method}",
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                )
            return resp.json()
        except Exception:
            logger.warning("[slack] %s request failed", method, exc_info=True)
            return {"ok": False, "error": "request_failed"}

    async def _open_agents_modal(self, trigger_id: str, channel_id: str) -> bool:
        """Open the /agents picker modal. Returns False (caller falls back to the plain
        ephemeral list) when there are no agents or ``views.open`` failed."""
        agents = await self._list_agents()
        if not agents:
            return False
        body = await self._slack_api(
            "views.open",
            {"trigger_id": trigger_id, "view": _build_agents_modal(agents, channel_id)},
        )
        if not body.get("ok"):
            logger.warning("[slack] views.open failed: %s", body.get("error"))
        return bool(body.get("ok"))


DSlackGatewayUseCase = Annotated[SlackGatewayUseCase, Depends(SlackGatewayUseCase)]
