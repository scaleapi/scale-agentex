"""Linear gateway — a platform-side ingress that fronts one Linear agent app
(``@agentex``) and routes each turn to the resolved agent runtime.

Direct analog of the Slack gateway (``slack_gateway_use_case``): an external trigger
that does ``task/create`` (get-or-create by name) then ``event/send`` against an
arbitrary agent via ``AgentsACPUseCase.handle_rpc_request``, with an idempotency
marker so provider retries don't double-deliver. Here the trigger is a Linear
``AgentSessionEvent`` (the app was @mentioned / assigned) instead of a Slack event.

Differences from Slack, all isolated to ingress/normalize/deliver:
  - Inbound auth is Linear's ``Linear-Signature`` (hex HMAC-SHA256 over the raw body)
    plus a ``webhookTimestamp`` freshness check. No url_verification handshake.
  - Dedup is on the ``Linear-Delivery`` UUID.
  - The reply is a Linear **agent activity** (``agentActivityCreate``): a ``thought``
    emitted immediately (Linear marks a session unresponsive without an activity
    within ~10s), then a ``response`` (terminal) when the turn settles — instead of
    a Slack ``chat.postMessage``.
  - The Linear API token is minted via the OAuth **client_credentials** grant with
    ``actor=app`` (the bot's own identity) and re-minted on a 401 — so no perishable
    token is stored, only the static client id/secret.

Identity: every Linear turn acts as the gateway's own SGP identity — a dedicated bot
service account (``LINEAR_GATEWAY_ACTING_BOT_API_KEY`` + ``LINEAR_GATEWAY_ACCOUNT_ID``,
env / k8s-secret only), forwarded as ``x-api-key`` and converted downstream to
``x-acting-user-api-key``. The bot is a first-class entity, not a proxy for the
invoking Linear user; its tasks are owned by it. Deliberately NOT per-user.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
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
from src.domain.entities.agents import ACPType
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

# The registered golden agent is "golden-agent" (hyphenated), same as the Slack path.
_DEFAULT_AGENT_NAME = "golden-agent"

# Every Linear turn acts as the gateway's own SGP identity — a dedicated bot service
# account. Forwarded as x-api-key (+ x-selected-account-id); converted downstream to
# x-acting-user-api-key so the agent's tools act as the bot. Env / k8s-secret only.
_ACTING_BOT_API_KEY = os.getenv("LINEAR_GATEWAY_ACTING_BOT_API_KEY", "")
_ACTING_ACCOUNT_ID = os.getenv("LINEAR_GATEWAY_ACCOUNT_ID", "")

# DEV ONLY. Skip Linear-Signature verification so a hand-crafted payload can be POSTed
# to /linear/events without a real signature. Never enable outside a dev environment —
# it lets anyone invoke agents through the gateway unauthenticated.
_DEV_SKIP_VERIFY = os.getenv("LINEAR_GATEWAY_DEV_SKIP_VERIFY", "").lower() in (
    "1",
    "true",
    "yes",
)

# Linear webhook replay guard: reject a delivery whose ``webhookTimestamp`` (ms) is
# more than this far from now. Linear's guidance is 60s.
_WEBHOOK_MAX_AGE_MS = int(os.getenv("LINEAR_WEBHOOK_MAX_AGE_MS", "60000"))

_MESSAGE_PAGE = 200  # per-poll page size when collecting the reply

# Linear webhooks are at-least-once — dedup on the ``Linear-Delivery`` UUID via Redis
# with a short TTL so a retry can't start a duplicate turn.
_EVENT_DEDUP_TTL_SECONDS = int(os.getenv("LINEAR_EVENT_DEDUP_TTL", "600"))

# Create-race handling (two concurrent first turns for one session): the loser's
# get-or-create raises DuplicateItemError; retry with a short backoff so a lagging
# read replica catches up. Mirrors the Slack gateway.
_CREATE_RACE_ATTEMPTS = max(1, int(os.getenv("LINEAR_CREATE_RACE_ATTEMPTS", "4")))
_CREATE_RACE_BACKOFF_S = float(os.getenv("LINEAR_CREATE_RACE_BACKOFF_S", "0.25"))

# Selector cascade default: golden-agent + this agent_config id when nothing else
# matches. Same shape as the Slack gateway.
_DEFAULT_CONFIG_ID = os.getenv(
    "LINEAR_GATEWAY_DEFAULT_CONFIG_ID", "416f61d9-9587-46be-a1d8-0b0aba17eb6e"
)
# SGP API base for name -> config_id resolution. Empty (or no acting key) -> skipped.
_SGP_BASE_URL = os.getenv("LINEAR_GATEWAY_SGP_BASE_URL", "").rstrip("/")
_CONFIG_ID_CACHE: dict[tuple[str, str], str] = {}

# Linear OAuth app (client_credentials, actor=app) — the gateway mints the app token
# from these to call the Linear API, and re-mints on 401. Static; never expire.
_CLIENT_ID = os.getenv("LINEAR_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("LINEAR_CLIENT_SECRET", "")
_WEBHOOK_SIGNING_SECRET = os.getenv("LINEAR_WEBHOOK_SIGNING_SECRET", "")

_LINEAR_API_BASE = os.getenv("LINEAR_API_BASE", "https://api.linear.app").rstrip("/")
_LINEAR_SCOPES = "read,write,app:assignable,app:mentionable"
# Process-lifetime cache of the minted app token; cleared + re-minted on a 401.
_APP_TOKEN: dict[str, str] = {}

_AGENT_ACTIVITY_CREATE = """
mutation AgentActivityCreate($input: AgentActivityCreateInput!) {
  agentActivityCreate(input: $input) { success }
}
""".strip()


# --------------------------------------------------------------------------- shaping


@dataclass
class InboundLinear:
    session_id: str  # AgentSession id — the conversation / task key
    actor: str  # who triggered it (for attribution)
    text: str  # the prompt text
    selector: str | None  # first token (candidate agent_config / agent name)
    issue_id: str  # issue context for the agent's Linear tools (may be "")
    action: str  # "created" | "prompted"


def _extract_prompt(payload: dict[str, Any], action: str) -> str:
    """Pull the user's prompt out of an AgentSessionEvent.

    On ``prompted`` the follow-up message is in ``agentActivity.body``. On ``created``
    the trigger is a mention/delegation, so prefer the triggering comment body, then
    the issue title/description, then the formatted ``promptContext``."""
    if action == "prompted":
        return ((payload.get("agentActivity") or {}).get("body") or "").strip()
    session = payload.get("agentSession") or {}
    comment = session.get("comment") or {}
    if comment.get("body"):
        return str(comment["body"]).strip()
    issue = session.get("issue") or {}
    title, desc = issue.get("title") or "", issue.get("description") or ""
    if title or desc:
        return (f"{title}\n\n{desc}").strip()
    return str(
        session.get("promptContext") or payload.get("promptContext") or ""
    ).strip()


def normalize(payload: dict[str, Any]) -> InboundLinear | None:
    """Shape an ``AgentSessionEvent``. Returns None for events we ignore."""
    if payload.get("type") != "AgentSessionEvent":
        return None
    action = payload.get("action") or ""
    if action not in ("created", "prompted"):
        return None
    session = payload.get("agentSession") or {}
    session_id = session.get("id") or payload.get("agentSessionId") or ""
    if not session_id:
        return None
    text = _extract_prompt(payload, action)
    issue = session.get("issue") or {}
    return InboundLinear(
        session_id=session_id,
        actor=(session.get("creator") or {}).get("name")
        or (session.get("actor") or {}).get("name")
        or "",
        text=text,
        selector=text.split(maxsplit=1)[0] if text else None,
        issue_id=issue.get("id") or "",
        action=action,
    )


def verify_signature(
    signing_secret: str, signature: str, body: bytes, webhook_timestamp: Any
) -> bool:
    """Linear webhook auth: hex HMAC-SHA256 over the RAW body with the webhook signing
    secret, plus a ``webhookTimestamp`` (ms) freshness guard to prevent replay."""
    try:
        if abs(time.time() * 1000 - int(webhook_timestamp)) > _WEBHOOK_MAX_AGE_MS:
            return False
    except (TypeError, ValueError):
        return False
    expected = hmac.new(signing_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@dataclass
class Target:
    agent_name: str
    config_id: str | None = None

    def label(self) -> str:
        return self.agent_name


def _strip_selector(text: str, selector: str) -> str:
    """Drop the leading selector token once it has matched a target."""
    stripped = text.strip()
    if stripped.lower().startswith(selector.lower()):
        stripped = stripped[len(selector) :].lstrip()
    return stripped


def _turn_content(inbound: InboundLinear, prompt: str) -> str:
    """Prepend Linear context so the agent's Linear tools have the issue/session to act
    on. Harmless when no Linear tool is enabled."""
    context = (
        f"[Linear context] session_id={inbound.session_id} issue_id={inbound.issue_id}. "
        f"This message came from that Linear agent session; use your Linear tools with "
        f"this issue_id to read or update the issue."
    )
    return f"{context}\n\n{prompt}"


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


class LinearGatewayUseCase:
    """Runs every Linear turn as one dedicated bot identity (the API key above). No
    constructor deps — the ACP use case is built per-turn, bound to the resolved
    principal + delegation headers, in ``_dispatch``."""

    async def handle_linear_event(
        self,
        *,
        body: bytes,
        headers: dict[str, str],
        payload: dict[str, Any],
        background: BackgroundTasks,
    ) -> dict:
        # 1. Verify the signature (unless dev-skip). No url_verification handshake.
        if _DEV_SKIP_VERIFY:
            logger.warning(
                "LINEAR_GATEWAY_DEV_SKIP_VERIFY is ON — skipping signature verification. "
                "DEV ONLY; the gateway is unauthenticated in this mode."
            )
        elif not verify_signature(
            _WEBHOOK_SIGNING_SECRET,
            headers.get("linear-signature", ""),
            body,
            payload.get("webhookTimestamp"),
        ):
            logger.warning("linear signature verification failed")
            return {"ok": False}  # 200 to Linear, but drop it

        inbound = normalize(payload)
        if inbound is None:
            return {"ok": True}  # event we don't act on

        # 2. Dedup Linear's at-least-once delivery on the Linear-Delivery UUID.
        delivery_id = headers.get("linear-delivery") or payload.get("webhookId")
        if await self._already_processed(delivery_id):
            logger.info("[linear] duplicate delivery %s skipped", delivery_id)
            return {"ok": True}

        # 3. ACK fast; run the turn out-of-band (it emits a `thought` within Linear's
        #    ~10s window before the longer dispatch).
        background.add_task(self._run_turn, inbound)
        return {"ok": True}

    async def _already_processed(self, delivery_id: str | None) -> bool:
        """Dedup on the Linear-Delivery UUID via a Redis ``SET NX`` with a short TTL.
        Returns True when the id was already seen. Fail-open (False) with no id / no
        Redis / any error, so dedup can never drop a legitimate first delivery."""
        if not delivery_id:
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
                f"linear:dedup:{delivery_id}", "1", nx=True, ex=_EVENT_DEDUP_TTL_SECONDS
            )
            return not first_time
        except Exception:  # noqa: BLE001 - dedup is best-effort; never block a turn
            logger.warning(
                "[linear] delivery dedup check failed; processing anyway", exc_info=True
            )
            return False

    async def _run_turn(self, inbound: InboundLinear) -> None:
        try:
            # Emit a `thought` first thing — Linear marks the session unresponsive
            # without an activity within ~10s, and this shows the agent is working.
            await self._emit(inbound, "thought", "On it…")

            principal, auth_headers = await self._acting_identity()
            target, prompt = await self._resolve_target(inbound, auth_headers)
            if not await self._authorize(target):
                await self._emit(
                    inbound, "error", f"You're not authorized to run {target.label()}."
                )
                return

            reply = await self._dispatch(
                target, inbound, prompt, principal, auth_headers
            )
            note = f"_via {target.label()}_"
            await self._emit(
                inbound,
                "response",
                f"{reply}\n\n{note}"
                if reply
                else f"_(no reply from {target.label()})_",
            )
        except Exception:
            logger.exception("linear gateway turn failed")
            await self._emit(
                inbound, "error", "Something went wrong handling that. Please retry."
            )

    async def _resolve_config_id(
        self, name: str, auth_headers: dict[str, str]
    ) -> str | None:
        """Resolve an agent_config NAME -> id via SGP's directory, authenticated with the
        acting identity's headers. Cached by (account, name). Fail-safe -> None (no SGP
        base / no acting key / any error) so the caller falls back to the default id."""
        api_key = auth_headers.get("x-api-key")
        if not (_SGP_BASE_URL and name and api_key):
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
            logger.warning("[linear] no agent_config named %r in SGP", name)
        except Exception:  # noqa: BLE001 - best-effort; fall back to the default id
            logger.warning(
                "[linear] config-id resolution failed for %r", name, exc_info=True
            )
        return None

    async def _message_send_with_race_retry(self, acp, params, agent_id):
        """Send a SYNC agent's ``message/send`` (get-or-creates the task, returns the
        reply), retrying the whole call on the create-race with a short backoff so a
        lagging replica catches up. Each raising attempt fails on the insert before
        appending, so retries never duplicate the turn's message."""
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
        raise last

    async def _resolve_task_after_race(self, task_service, task_name: str):
        """Resolve the winner's task by name after an async-path create-race. Retry on
        ItemDoesNotExist with backoff until the (possibly-lagging) replica catches up."""
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
        inbound: InboundLinear,
        prompt: str,
        principal: Any,
        auth_headers: dict[str, str],
    ) -> str | None:
        """Create-or-resume a task on the resolved agent, then inject the turn. Keyed on
        the Linear agent session (``linear:{session_id}``). ASYNC/AGENTIC agents get a
        long-lived workflow (TASK_CREATE first turn, then event/send + poll); SYNC agents
        get one message/send. Slack-origin gating in golden-agent auto-enables the
        Linear-only tools off ``task_metadata.channel == "linear"`` — the gateway never
        requests them."""
        # Local import avoids a domain -> temporal import cycle at module load.
        from src.temporal.scheduled_agent_run_factory import (
            build_acp_use_case_for_principal,
        )

        acp = build_acp_use_case_for_principal(
            GlobalDependencies(), principal, request_headers=auth_headers
        )
        agent = await acp.agent_repository.get(name=target.agent_name)
        task_name = f"linear:{inbound.session_id}"
        content = TextContentEntity(
            author=MessageAuthor.USER,
            content=_turn_content(inbound, prompt),
            format=TextFormat.MARKDOWN,
        )
        create_params: dict[str, Any] = {}
        if target.config_id:
            create_params["config_id"] = target.config_id

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
                "channel": "linear",
                "sender_id": target.label(),
                "session_id": inbound.session_id,
                "issue_id": inbound.issue_id,
            }
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
                task = await self._resolve_task_after_race(acp.task_service, task_name)

        seen = await self._seen_message_ids(acp.task_message_service, task.id)
        await acp.handle_rpc_request(
            method=AgentRPCMethod.EVENT_SEND,
            params=SendEventRequestEntity(task_name=task_name, content=content),
            agent_id=agent.id,
        )
        return await self._collect_reply(acp.task_message_service, task.id, seen)

    async def _existing_task(self, task_service, name: str):
        try:
            return await task_service.get_task(name=name)
        except ItemDoesNotExist:
            return None

    async def _recent_messages(self, msg_service, task_id: str) -> list:
        """Newest page of task messages in chronological order (fetch DESC so this turn's
        reply is always in the window even on a long task, then reverse)."""
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
        for quiescence_s) or times out. Filters on ids not present before the event."""
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
        """The gateway's bot identity. Bot API key + account from env / k8s-secret.
        Verify the key -> principal, return the credential headers (delegated downstream
        as x-acting-user-api-key). FAIL CLOSED when authz is enabled (AGENTEX_AUTH_URL
        set) but the key is missing, so a misconfigured deploy never dispatches
        unauthenticated. Only the authz-off local case runs with no principal."""
        api_key = _ACTING_BOT_API_KEY
        if not api_key:
            if os.getenv("AGENTEX_AUTH_URL"):
                raise RuntimeError(
                    "LINEAR_GATEWAY_ACTING_BOT_API_KEY is unset while authz is enabled "
                    "(AGENTEX_AUTH_URL); refusing to dispatch a Linear turn without a "
                    "bot principal."
                )
            return None, {}
        account_id = _ACTING_ACCOUNT_ID
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

    async def _resolve_target(
        self, inbound: InboundLinear, auth_headers: dict[str, str]
    ) -> tuple[Target, str]:
        """Selector cascade for the leading token: SGP agent_config name -> golden-agent
        + that config; else a registered agentex agent -> that runtime; else golden-agent
        + the default config. The selector is stripped only when it matched."""
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
        """Runtime-registry tier: does an agent with this name exist? Credential-free
        read (the directory is infrastructure); access control is enforced at dispatch."""
        engine = database_async_read_write_engine()
        repo = AgentRepository(
            database_async_read_write_session_maker(engine),
            database_async_read_only_session_maker(engine),
        )
        try:
            return await repo.get(name=name)
        except ItemDoesNotExist:
            return None

    async def _authorize(self, target: Target) -> bool:
        # The acting identity's own grants are enforced by the ACP use case's internal
        # authz (agent.execute / task.*). No extra gate here.
        return True

    async def _app_token(self, *, force_refresh: bool = False) -> str:
        """Mint (and cache) the Linear API token via the OAuth client_credentials grant.
        The token is INHERENTLY an app-actor token (the bot's own identity) — do NOT pass
        ``actor=app`` here; that param belongs to the authorization_code flow and Linear
        rejects/ignores it on client_credentials. Re-minted when ``force_refresh`` (a 401
        from the API means the ~30-day token expired). No perishable token is stored, only
        the static client id/secret in env."""
        if not force_refresh and _APP_TOKEN.get("token"):
            return _APP_TOKEN["token"]
        if not (_CLIENT_ID and _CLIENT_SECRET):
            logger.warning("[linear] no client id/secret configured; cannot mint token")
            return ""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{_LINEAR_API_BASE}/oauth/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": _CLIENT_ID,
                        "client_secret": _CLIENT_SECRET,
                        "scope": _LINEAR_SCOPES,
                    },
                )
            token = (resp.json() or {}).get("access_token") or ""
        except Exception:  # noqa: BLE001 - surfaced as an empty token -> activity no-op
            logger.warning("[linear] app-token mint failed", exc_info=True)
            return ""
        if token:
            _APP_TOKEN["token"] = token
        return token

    async def _emit(
        self, inbound: InboundLinear, activity_type: str, body: str
    ) -> None:
        """Post an agent activity (``thought`` / ``response`` / ``error``) onto the
        session via ``agentActivityCreate``. Mints the app token, and re-mints + retries
        once on a 401 (expired client_credentials token). Best-effort: logged, never
        fatal to the turn."""
        for attempt in range(2):
            token = await self._app_token(force_refresh=attempt == 1)
            if not token:
                logger.info(
                    "[linear] no app token — would emit %s -> session %s: %s",
                    activity_type,
                    inbound.session_id,
                    body[:200],
                )
                return
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(
                        f"{_LINEAR_API_BASE}/graphql",
                        headers={"Authorization": f"Bearer {token}"},
                        json={
                            "query": _AGENT_ACTIVITY_CREATE,
                            "variables": {
                                "input": {
                                    "agentSessionId": inbound.session_id,
                                    "content": {"type": activity_type, "body": body},
                                }
                            },
                        },
                    )
            except Exception:  # noqa: BLE001 - never let delivery break the turn
                logger.warning(
                    "[linear] agentActivityCreate request failed", exc_info=True
                )
                return
            if resp.status_code == 401 and attempt == 0:
                continue  # token expired — re-mint and retry once
            data = resp.json() if resp.content else {}
            if resp.status_code == 200 and not data.get("errors"):
                logger.info(
                    "[linear] emitted %s -> session %s",
                    activity_type,
                    inbound.session_id,
                )
            else:
                logger.warning(
                    "[linear] agentActivityCreate failed (%s): %s",
                    resp.status_code,
                    (data.get("errors") if data else resp.text)[:300]
                    if data or resp.text
                    else "",
                )
            return


DLinearGatewayUseCase = Annotated[LinearGatewayUseCase, Depends(LinearGatewayUseCase)]
