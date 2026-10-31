"""Renewable Azure Workload Identity authentication for Temporal clients."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from azure.core.credentials import AccessToken
from azure.identity.aio import WorkloadIdentityCredential
from temporalio.client import Client

logger = logging.getLogger(__name__)

_AUTH_SCOPE_ENV = "TEMPORAL_AUTH_SCOPE"
_REFRESH_MARGIN_SECONDS = 300
_MIN_REFRESH_DELAY_SECONDS = 30
_RETRY_DELAY_SECONDS = 30


class AsyncTokenCredential(Protocol):
    """Credential surface needed by the refresher."""

    async def get_token(self, *scopes: str) -> AccessToken: ...

    async def close(self) -> None: ...


@dataclass(eq=False)
class TemporalTokenSession:
    """Keep a Temporal client's bearer token current for the process lifetime."""

    client: Client
    credential: AsyncTokenCredential
    scope: str
    token: AccessToken
    now: Callable[[], float] = time.time
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    _task: asyncio.Task[None] | None = field(default=None, init=False)

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())
        _ACTIVE_SESSIONS.add(self)
        self._task.add_done_callback(lambda _: _ACTIVE_SESSIONS.discard(self))

    async def refresh_once(self) -> bool:
        """Replace the token only after a valid refresh succeeds."""
        try:
            refreshed = await self.credential.get_token(self.scope)
            if refreshed.expires_on <= self.now():
                raise ValueError("Azure returned an expired Temporal access token")
        except Exception:
            log = (
                logger.error if self.token.expires_on <= self.now() else logger.warning
            )
            log(
                "Temporal access token refresh failed; retaining the current token",
                exc_info=True,
            )
            return False

        self.client.api_key = refreshed.token
        self.token = refreshed
        return True

    async def _run(self) -> None:
        try:
            while True:
                refresh_in = max(
                    _MIN_REFRESH_DELAY_SECONDS,
                    self.token.expires_on - self.now() - _REFRESH_MARGIN_SECONDS,
                )
                await self.sleep(refresh_in)
                if not await self.refresh_once():
                    await self.sleep(_RETRY_DELAY_SECONDS)
        finally:
            await self.credential.close()


_ACTIVE_SESSIONS: set[TemporalTokenSession] = set()


async def connect_temporal_client(connect_options: dict[str, Any]) -> Client:
    """Connect anonymously by default, or with renewable Workload Identity."""
    scope = os.environ.get(_AUTH_SCOPE_ENV)
    if not scope:
        return await Client.connect(**connect_options)

    credential = WorkloadIdentityCredential()
    try:
        token = await credential.get_token(scope)
        if token.expires_on <= time.time():
            raise ValueError("Azure returned an expired Temporal access token")
        authenticated_options = dict(connect_options)
        if authenticated_options.get("tls") is None:
            authenticated_options["tls"] = False
        client = await Client.connect(api_key=token.token, **authenticated_options)
    except Exception:
        await credential.close()
        raise

    TemporalTokenSession(
        client=client,
        credential=credential,
        scope=scope,
        token=token,
    ).start()
    return client
