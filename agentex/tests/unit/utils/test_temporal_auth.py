from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.core.credentials import AccessToken
from src.utils.temporal_auth import TemporalTokenSession, connect_temporal_client
from temporalio.client import TLSConfig

_SCOPE = "api:" + "//example.invalid/.default"
_INITIAL = "fixture" + "-initial"
_RENEWED = "fixture" + "-renewed"


class FakeCredential:
    def __init__(self, result):
        self.result = result
        self.closed = False

    async def get_token(self, _scope):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def close(self):
        self.closed = True


async def test_connect_without_scope_preserves_legacy_path(monkeypatch):
    monkeypatch.delenv("TEMPORAL_AUTH_SCOPE", raising=False)
    client = MagicMock()

    with (
        patch("src.utils.temporal_auth.WorkloadIdentityCredential") as credential,
        patch(
            "src.utils.temporal_auth.Client.connect", new=AsyncMock(return_value=client)
        ) as connect,
    ):
        result = await connect_temporal_client({"target_host": "temporal:7233"})

    assert result is client
    credential.assert_not_called()
    connect.assert_awaited_once_with(target_host="temporal:7233")


async def test_connect_initial_token_failure_blocks_startup(monkeypatch):
    monkeypatch.setenv("TEMPORAL_AUTH_SCOPE", _SCOPE)
    credential = FakeCredential(RuntimeError("identity unavailable"))

    with (
        patch(
            "src.utils.temporal_auth.WorkloadIdentityCredential",
            return_value=credential,
        ),
        patch("src.utils.temporal_auth.Client.connect", new=AsyncMock()) as connect,
        pytest.raises(RuntimeError, match="identity unavailable"),
    ):
        await connect_temporal_client({"target_host": "temporal:7233"})

    connect.assert_not_awaited()
    assert credential.closed is True


async def test_connect_expired_initial_token_blocks_startup(monkeypatch):
    monkeypatch.setenv("TEMPORAL_AUTH_SCOPE", _SCOPE)
    credential = FakeCredential(AccessToken(_INITIAL, 999))

    with (
        patch("src.utils.temporal_auth.time.time", return_value=1_000),
        patch(
            "src.utils.temporal_auth.WorkloadIdentityCredential",
            return_value=credential,
        ),
        patch("src.utils.temporal_auth.Client.connect", new=AsyncMock()) as connect,
        pytest.raises(ValueError, match="expired Temporal access token"),
    ):
        await connect_temporal_client({"target_host": "temporal:7233"})

    connect.assert_not_awaited()
    assert credential.closed is True


async def test_connect_sends_initial_token_over_plaintext(monkeypatch):
    monkeypatch.setenv("TEMPORAL_AUTH_SCOPE", _SCOPE)
    access = AccessToken(_INITIAL, 2_000)
    credential = FakeCredential(access)
    client = MagicMock()

    with (
        patch("src.utils.temporal_auth.time.time", return_value=1_000),
        patch(
            "src.utils.temporal_auth.WorkloadIdentityCredential",
            return_value=credential,
        ),
        patch(
            "src.utils.temporal_auth.Client.connect", new=AsyncMock(return_value=client)
        ) as connect,
        patch.object(TemporalTokenSession, "start") as start,
    ):
        result = await connect_temporal_client({"target_host": "temporal:7233"})

    assert result is client
    connect.assert_awaited_once_with(
        target_host="temporal:7233", tls=False, api_key=_INITIAL
    )
    start.assert_called_once()


async def test_connect_preserves_explicit_tls(monkeypatch):
    monkeypatch.setenv("TEMPORAL_AUTH_SCOPE", _SCOPE)
    access = AccessToken(_INITIAL, 2_000)
    credential = FakeCredential(access)
    client = MagicMock()
    tls = TLSConfig(server_root_ca_cert=b"fixture-ca")

    with (
        patch("src.utils.temporal_auth.time.time", return_value=1_000),
        patch(
            "src.utils.temporal_auth.WorkloadIdentityCredential",
            return_value=credential,
        ),
        patch(
            "src.utils.temporal_auth.Client.connect", new=AsyncMock(return_value=client)
        ) as connect,
        patch.object(TemporalTokenSession, "start") as start,
    ):
        result = await connect_temporal_client(
            {"target_host": "temporal:7233", "tls": tls}
        )

    assert result is client
    connect.assert_awaited_once_with(
        target_host="temporal:7233", tls=tls, api_key=_INITIAL
    )
    start.assert_called_once()


async def test_refresh_replaces_the_client_token():
    client = MagicMock(api_key=_INITIAL)
    renewed = AccessToken(_RENEWED, 3_000)
    credential = FakeCredential(renewed)
    initial = AccessToken(_INITIAL, 2_000)
    session = TemporalTokenSession(
        client=client,
        credential=credential,
        scope=_SCOPE,
        token=initial,
        now=lambda: 1_000,
    )

    refreshed = await session.refresh_once()

    assert refreshed is True
    assert client.api_key == _RENEWED


async def test_refresh_failure_never_clears_authentication():
    client = MagicMock(api_key=_INITIAL)
    credential = FakeCredential(RuntimeError("identity unavailable"))
    initial = AccessToken(_INITIAL, 900)
    session = TemporalTokenSession(
        client=client,
        credential=credential,
        scope=_SCOPE,
        token=initial,
        now=lambda: 1_000,
    )

    refreshed = await session.refresh_once()

    assert refreshed is False
    assert client.api_key == _INITIAL


async def test_refresh_expired_replacement_never_clears_authentication():
    client = MagicMock(api_key=_INITIAL)
    credential = FakeCredential(AccessToken(_RENEWED, 999))
    initial = AccessToken(_INITIAL, 2_000)
    session = TemporalTokenSession(
        client=client,
        credential=credential,
        scope=_SCOPE,
        token=initial,
        now=lambda: 1_000,
    )

    refreshed = await session.refresh_once()

    assert refreshed is False
    assert client.api_key == _INITIAL
