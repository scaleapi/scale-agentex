"""ChannelRouter: turn a normalized InboundMessage into an agent turn, and (for
channels that respond) retrieve the agent's reply.

Channel-agnostic — the same path serves webhook, Slack, or any future channel.
Works for both ACP types: sync agents take the turn via message/send (reply returned
inline); async/agentic agents via event/send (reply lands on the task's message
stream, retrieved by `await_reply`). Continuity is free: the InboundMessage's
session_key is reused as the agentex task name (task/create is get-or-create on name).

A responding channel pairs this with the outbound side (OpenClaw deliver/chunker):
    result = await router.dispatch(inbound, binding, acp_type)
    reply = result.reply or await router.await_reply(result.task_id, result.after_id)
    await deliver_reply(channel, inbound.peer_id, reply)   # chunk + deliver per block
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from src.domain.channels.base import ChannelBinding, InboundMessage
from src.domain.entities.agents import ACPType
from src.domain.entities.agents_rpc import (
    AgentRPCMethod,
    CreateTaskRequestEntity,
    SendEventRequestEntity,
    SendMessageRequestEntity,
)
from src.domain.entities.task_messages import (
    MessageAuthor,
    TaskMessageContentType,
    TextContentEntity,
)
from src.domain.services.task_message_service import TaskMessageService
from src.domain.use_cases.agents_acp_use_case import AgentsACPUseCase
from src.utils.logging import make_logger

logger = make_logger(__name__)


@dataclass
class DispatchResult:
    task_id: str
    # Sync agents return their reply inline. Async agents reply later on the task
    # stream — `reply` is None and `after_id` marks where to read new messages from.
    reply: str | None = None
    after_id: str | None = None


class ChannelRouter:
    def __init__(
        self,
        acp_use_case: AgentsACPUseCase,
        task_message_service: TaskMessageService,
    ):
        self._acp = acp_use_case
        self._messages = task_message_service

    async def dispatch(
        self, inbound: InboundMessage, binding: ChannelBinding, acp_type: ACPType
    ) -> DispatchResult:
        session_key = inbound.session_key(binding.agent_name)
        headers = binding.forward_headers or None

        task = await self._acp.handle_rpc_request(
            method=AgentRPCMethod.TASK_CREATE,
            params=CreateTaskRequestEntity(
                name=session_key,
                params=binding.params,
                task_metadata={
                    "channel": inbound.channel,
                    "route_id": inbound.route_id,
                    "peer_id": inbound.peer_id,
                    "sender_id": inbound.sender_id,
                },
            ),
            agent_name=binding.agent_name,
            request_headers=headers,
        )
        task_id = task.id
        logger.info(
            "[channels] %s route=%s acp=%s -> task %s (session %s)",
            inbound.channel,
            inbound.route_id,
            acp_type.value,
            task_id,
            session_key,
        )

        content = TextContentEntity(author=MessageAuthor.USER, content=inbound.text)

        if acp_type == ACPType.SYNC:
            # Sync: message/send carries the turn and returns the reply messages inline.
            messages = await self._acp.handle_rpc_request(
                method=AgentRPCMethod.MESSAGE_SEND,
                params=SendMessageRequestEntity(
                    task_id=task_id, content=content, stream=False
                ),
                agent_name=binding.agent_name,
                request_headers=headers,
            )
            return DispatchResult(task_id=task_id, reply=_agent_text(messages))

        # Async / agentic: event/send delivers the turn; the reply lands on the stream.
        # Mark the newest message now so await_reply only reads the new reply.
        after_id = await self._newest_message_id(task_id)
        await self._acp.handle_rpc_request(
            method=AgentRPCMethod.EVENT_SEND,
            params=SendEventRequestEntity(task_id=task_id, content=content),
            agent_name=binding.agent_name,
            request_headers=headers,
        )
        return DispatchResult(task_id=task_id, reply=None, after_id=after_id)

    async def _newest_message_id(self, task_id: str) -> str | None:
        msgs = await self._messages.get_messages(
            task_id=task_id, limit=1, page_number=1
        )
        return msgs[0].id if msgs else None

    async def await_reply(
        self,
        task_id: str,
        after_id: str | None = None,
        timeout_s: float = 120.0,
        interval_s: float = 2.0,
        quiescence_s: float = 6.0,
    ) -> str | None:
        """Poll the task's messages for the agent's text reply after `after_id`, until
        it settles (no change for `quiescence_s`) or `timeout_s`. Used by responding
        channels to retrieve an async agent's reply before delivering it."""
        waited = 0.0
        last: str | None = None
        stable_for = 0.0
        while waited < timeout_s:
            await asyncio.sleep(interval_s)
            waited += interval_s
            msgs = await self._messages.get_messages(
                task_id=task_id,
                limit=100,
                page_number=1,
                order_direction="asc",
                after_id=after_id,
            )
            text = _agent_text(msgs)
            if text and text == last:
                stable_for += interval_s
                if stable_for >= quiescence_s:
                    return text
            elif text:
                last = text
                stable_for = 0.0
        return last


def _is_agent_text(message: object) -> bool:
    content = getattr(message, "content", None)
    return (
        content is not None
        and getattr(content, "type", None) == TaskMessageContentType.TEXT
        and getattr(content, "author", None) == MessageAuthor.AGENT
        and bool((getattr(content, "content", "") or "").strip())
    )


def _agent_text(messages: object) -> str | None:
    """Join the agent-authored text from a message list (sync result or polled stream)."""
    if not isinstance(messages, list):
        return None
    parts = [m.content.content.strip() for m in messages if _is_agent_text(m)]
    return "\n\n".join(parts) if parts else None
