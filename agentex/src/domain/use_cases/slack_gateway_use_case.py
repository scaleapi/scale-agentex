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

v1 identity: every Slack turn acts as ONE shared SGP identity — the acting-user API
key (``SLACK_GATEWAY_ACTING_USER_API_KEY``, env/secret only). It's forwarded as
``x-api-key``, which the platform (a) verifies -> principal for authz and (b) converts
to ``x-acting-user-api-key`` so the agent's tools act as that user via
resolve_user_secrets. Everyone shares its access: fine for a controlled internal
deploy, NOT customer/multi-tenant. STILL STUBBED (marked TODO): the signing-secret/
bot-token fetch (sgp-secrets microservice), name->config resolution against
``agent_configs``, and reply delivery. Dispatch, delegation, and idempotency are real.

Future — per-user identity (post-v1): resolve the Slack user -> SGP user via a verified
link. When a user is unlinked, nudge them with an **ephemeral in-channel message**
(``chat.postEphemeral`` — needs only ``chat:write``, no DM/``im:write``) carrying a
signed one-time link to ``/link/slack``; the SGP OIDC login on that page proves the SGP
side and the callback writes ``(team_id, slack_user_id) -> sgp_user_id``. Don't dispatch
until linked.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
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
from src.domain.entities.agent_api_keys import AgentAPIKeyType
from src.domain.entities.agents import AgentStatus
from src.domain.entities.agents_rpc import (
    AgentRPCMethod,
    CreateTaskRequestEntity,
    SendEventRequestEntity,
)
from src.domain.entities.task_messages import (
    MessageAuthor,
    TextContentEntity,
    TextFormat,
)
from src.domain.repositories.agent_api_key_repository import AgentAPIKeyRepository
from src.domain.repositories.agent_repository import AgentRepository
from src.utils.logging import make_logger

logger = make_logger(__name__)

_MENTION_RE = re.compile(r"^\s*<@[A-Z0-9]+>\s*")
# agentex agent names are hyphenated (e.g. "dbt-assistant"); the registered golden
# agent is "golden-agent", not "golden_agent" (verified against the sgp-dev directory).
_DEFAULT_AGENT_NAME = "golden-agent"

# v1: every Slack turn acts as ONE shared SGP identity — this acting-user API key.
# Forwarded as x-api-key: the platform verifies it -> principal (authz) and converts it
# to x-acting-user-api-key downstream (tools act as that user via resolve_user_secrets).
# Everyone shares its access — controlled-internal only, NOT customer/multi-tenant.
# Secret lives in env only, never in code. TODO: replace with a per-user key resolved
# from verified Slack->SGP linking.
_ACTING_USER_API_KEY = os.getenv("SLACK_GATEWAY_ACTING_USER_API_KEY", "")

# Account the shared identity acts within. REQUIRED alongside the API key — the backend
# authenticates on (x-api-key + x-selected-account-id) together; the key alone 401s
# (verified against sgp-dev). Also forwarded downstream so the agent runs in this account.
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

# Slack's HTTP Events API is at-least-once — it retries a delivery (up to ~3x, with an
# X-Slack-Retry-Num header) if we don't 200 within ~3s. Dedup on the envelope's
# ``event_id`` via Redis with a short TTL so a retry can't start a duplicate turn.
_EVENT_DEDUP_TTL_SECONDS = int(os.getenv("SLACK_EVENT_DEDUP_TTL", "600"))

# v1/dev: golden-agent requires a system prompt (task/create params or turn-1 config).
# Until name->config resolution lands (tier 2), pass this default so the turn can run.
_DEFAULT_SYSTEM_PROMPT = os.getenv(
    "SLACK_GATEWAY_DEFAULT_SYSTEM_PROMPT",
    (
        "You are Golden 🌟 — a friendly, upbeat teammate hanging out in Slack. Bring "
        "personality and sprinkle in plentiful, fitting emojis. When you're working "
        "through a task, narrate your progress with a little flair (e.g. 'On it! 🔍', "
        "'Digging through the channel… 🧵', 'Crunching the details… ⚙️', 'Done! ✅'). "
        "Keep replies concise and easy to skim in chat, and use your Slack tools to read "
        "channel history, threads, or files whenever it helps 🛠️. Stay genuinely useful "
        "first — the playfulness is seasoning, never a substitute for a clear, correct "
        "answer. 🎉"
    ),
)

# v1/dev: MCP tools to enable per task (golden-agent switches MCPs on from the config's
# `mcps` list; the credential existing isn't enough — the tool must be enabled for the
# task). Comma-separated MCPServer names, e.g. SLACK_GATEWAY_DEFAULT_MCPS=Slack.
# TODO: comes from the resolved agent_config once tier-2 lands.
_DEFAULT_MCPS = [
    m.strip()
    for m in os.getenv("SLACK_GATEWAY_DEFAULT_MCPS", "").split(",")
    if m.strip()
]

# Fixed, descriptive names for the gateway's own Slack credentials in the throwaway
# agent_api_keys store. One shared app, so we key by these readable names rather than
# the cryptic api_app_id (also avoids colliding with per-agent webhook rows, which use
# name=api_app_id). TODO: replace this whole store with sgp-secrets user-scope.
_BOT_TOKEN_NAME = "slack-bot-token"
_SIGNING_SECRET_NAME = "slack-signing-secret"
# v1 shared acting identity (SGP acting-user API key + account) — same throwaway
# DB store as the tokens, so a deployed (authz-on) gateway can dispatch with a real
# principal. Not a Slack token, but kept in the one gateway-config store for now.
_ACTING_API_KEY_NAME = "slack-acting-user-api-key"
_ACTING_ACCOUNT_ID_NAME = "slack-acting-account-id"


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
        return (
            f"{self.agent_name}/{self.config_id}" if self.config_id else self.agent_name
        )


def _strip_selector(text: str, selector: str) -> str:
    """Drop the leading selector token once it has matched a target."""
    stripped = text.strip()
    if stripped.lower().startswith(selector.lower()):
        stripped = stripped[len(selector) :].lstrip()
    return stripped


def _turn_content(inbound: InboundSlack, prompt: str) -> str:
    """Prepend the Slack conversation context to the turn.

    normalize() is otherwise lossy — it hands the agent only the prompt text and drops
    the channel/thread. But to read channel history the agent needs the channel id to
    point its Slack tools at, so we prefix a short, clearly-delimited context line and
    put the user's message after a blank line. Harmless when no Slack tool is enabled."""
    context = (
        f"[Slack context] channel_id={inbound.channel} thread_ts={inbound.thread_ts}. "
        f"This message came from that Slack thread; to read earlier messages or the "
        f"channel's history, use your Slack tools with this channel_id."
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
            return _agents_list_response(await self._list_agents())
        return {
            "response_type": "ephemeral",
            "text": f"Unsupported command: {command or '(none)'}",
        }

    async def _run_turn(self, inbound: InboundSlack) -> None:
        try:
            account_id = await self._resolve_account(inbound.team_id)
            target, prompt = await self._resolve_target(account_id, inbound)

            if not await self._authorize(target):
                await self._deliver(
                    inbound, f"You're not authorized to run {target.label()}."
                )
                return

            # AI-app "thinking…" indicator while the turn runs (assistant pane); cleared
            # automatically when we post the reply. No-op outside an assistant thread.
            await self._set_status(inbound, "is thinking…")
            reply = await self._dispatch(target, inbound, prompt)
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

    async def _dispatch(
        self, target: Target, inbound: InboundSlack, prompt: str
    ) -> str | None:
        """Create-or-resume a task on the resolved agent, then inject the turn, acting as
        the shared v1 identity (x-api-key -> principal for authz, delegated downstream as
        x-acting-user-api-key so tools act as that user).

        The task is keyed on the Slack thread (``slack:{thread_ts}``), so a thread is one
        long-lived task/workflow. TASK_CREATE runs only on the FIRST turn; follow-ups in
        the same thread skip it (the workflow is already running — re-creating raises
        WorkflowAlreadyStarted) and just send the next event.

        TODO: dedup on Slack's event_id — the Events API is at-least-once, so a
        retried delivery could otherwise start a duplicate turn.
        """
        # Local import avoids a domain -> temporal import cycle at module load.
        from src.temporal.scheduled_agent_run_factory import (
            build_acp_use_case_for_principal,
        )

        principal, delegation_headers = await self._acting_identity()
        acp = build_acp_use_case_for_principal(
            GlobalDependencies(), principal, request_headers=delegation_headers
        )
        agent = await acp.agent_repository.get(name=target.agent_name)
        thread_ts = inbound.thread_ts
        task_name = f"slack:{thread_ts}"

        task = await self._existing_task(acp.task_service, task_name)
        if task is None:
            # First turn in this thread → start the task/workflow.
            task_metadata = {
                "channel": "slack",
                "sender_id": target.label(),
                "thread_ts": thread_ts,
                "channel_id": inbound.channel,
            }
            if target.config_id:
                task_metadata["config_id"] = target.config_id
            # v1/dev: default system_prompt + optionally-enabled MCP tools.
            # TODO: resolve target.config_id -> full params (system_prompt / harness /
            # model / tools) via egp /v5/agent_configs/{id}/resolve.
            create_params = {"system_prompt": _DEFAULT_SYSTEM_PROMPT}
            if _DEFAULT_MCPS:
                create_params["mcps"] = _DEFAULT_MCPS
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
                # workflow starts). Fall back to the task it created and just send this
                # turn's event, exactly as a follow-up would.
                task = await acp.task_service.get_task(name=task_name)

        # Snapshot existing messages so we can isolate THIS turn's reply.
        seen = await self._seen_message_ids(acp.task_message_service, task.id)

        content = TextContentEntity(
            author=MessageAuthor.USER,
            content=_turn_content(inbound, prompt),
            format=TextFormat.MARKDOWN,
        )
        await acp.handle_rpc_request(
            method=AgentRPCMethod.EVENT_SEND,
            params=SendEventRequestEntity(task_name=task_name, content=content),
            agent_id=agent.id,
        )

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
        """v1 shared identity. The acting-user API key + account come from the DB
        (agent_api_keys, same throwaway store as the tokens), env fallback. Verify the
        key -> principal (for authz), and return the credential headers (delegated to
        the agent, where x-api-key becomes x-acting-user-api-key). Auth needs BOTH
        x-api-key and x-selected-account-id — the key alone 401s. No key configured ->
        (None, {}) i.e. dev/authz-bypass."""
        api_key = (
            await self._gateway_secret(_ACTING_API_KEY_NAME) or _ACTING_USER_API_KEY
        )
        if not api_key:
            return None, {}
        account_id = (
            await self._gateway_secret(_ACTING_ACCOUNT_ID_NAME) or _ACTING_ACCOUNT_ID
        )
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

    # --- STUBS (each is a real net-new piece; do NOT ship as-is) ----------------

    async def _gateway_secret(self, name: str) -> str:
        """Read a Slack gateway secret from the ``agent_api_keys`` table by (name,
        SLACK). THROWAWAY store — plaintext, reusing the existing table by naming
        convention (api_app_id = signing secret, api_app_id:bot = bot token) so it
        needs no migration. To be replaced by sgp-secrets user-scope. Fail-safe: any
        error (incl. no DB in unit tests) returns "" so callers fall back to env."""
        if not name:
            return ""
        try:
            engine = database_async_read_write_engine()
            repo = AgentAPIKeyRepository(
                database_async_read_write_session_maker(engine),
                database_async_read_only_session_maker(engine),
            )
            row = await repo.get_by_name_and_type(name, AgentAPIKeyType.SLACK)
            return row.api_key if row else ""
        except Exception:  # noqa: BLE001 - fail-safe to env fallback
            logger.debug(
                "gateway-secret DB read failed for %r; env fallback",
                name,
                exc_info=True,
            )
            return ""

    async def _fetch_signing_secret(self, api_app_id: str) -> str:
        # Throwaway DB store (agent_api_keys, name="slack-signing-secret", type SLACK);
        # env fallback for local dev. Empty => verify_signature fails closed. api_app_id
        # is unused (one shared app) but kept on the interface.
        return await self._gateway_secret(_SIGNING_SECRET_NAME) or os.getenv(
            "SLACK_SIGNING_SECRET", ""
        )

    async def _resolve_account(self, team_id: str) -> str:
        # TODO: Slack team_id -> SGP account (tenant-aware from day one). v1 derives the
        # account from the acting-user key's principal, so this is unused for now.
        return ""

    async def _resolve_target(
        self, account_id: str, inbound: InboundSlack
    ) -> tuple[Target, str]:
        """Resolution cascade:
        1. runtime registry — the selector names a separately-registered agent -> route
           to it (strip the selector; the rest is the prompt).
        2. TODO agent_configs by name -> golden_agent + config_id.
        3. default — golden_agent, whole message is the prompt.
        """
        selector = inbound.selector
        if selector and await self._get_agent_by_name(selector) is not None:
            return Target(agent_name=selector), _strip_selector(inbound.text, selector)
        return Target(agent_name=_DEFAULT_AGENT_NAME, config_id=None), inbound.text

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
        # Throwaway DB store (agent_api_keys, name="slack-bot-token", type SLACK); env
        # fallback for local dev.
        return await self._gateway_secret(_BOT_TOKEN_NAME) or os.getenv(
            "SLACK_BOT_TOKEN", ""
        )

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


DSlackGatewayUseCase = Annotated[SlackGatewayUseCase, Depends(SlackGatewayUseCase)]
