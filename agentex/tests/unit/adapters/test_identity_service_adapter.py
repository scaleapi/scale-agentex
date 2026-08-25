"""Unit tests for the identity-service key-minting client.

The single most valuable test here is the wrong-issuer guard. There are two API-key
issuers on the platform and only identity-service's ``ssk_`` keys are accepted by
sgp-secrets — a key from egp-api-backend authenticates fine against egp-api-backend
and then fails at the vault with an opaque 401. Storing one would produce a link
that looks healthy and silently can't read any secrets, so the client refuses
anything that isn't ``ssk_``-shaped.
"""

from datetime import UTC, datetime, timedelta

import pytest
from src.adapters.identity_service import adapter_identity_service as mod
from src.adapters.identity_service.adapter_identity_service import (
    IdentityServiceClient,
    IdentityServiceError,
    forwardable_headers,
)

_USER = "11111111-2222-4333-8444-555555555555"
_GOOD = "ssk_is_" + "a" * 32


def _fake_http(monkeypatch, *, status=200, body=None, raises=None, captured=None):
    class _Resp:
        status_code = status
        text = "" if body is None else "body"

        def json(self):
            if body is None:
                raise ValueError("no json")
            return body

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            if captured is not None:
                captured.update(url=url, json=json, headers=headers)
            if raises is not None:
                raise raises
            return _Resp()

    monkeypatch.setattr(mod.httpx, "AsyncClient", _Client)


@pytest.mark.unit
class TestBaseUrl:
    def test_unset_raises_rather_than_defaulting(self, monkeypatch):
        # No default on purpose: the address is deployment-specific, and guessing
        # wrong would POST the user's forwarded session credentials at whatever
        # host happens to answer.
        monkeypatch.delenv(mod.IDENTITY_SERVICE_URL_ENV, raising=False)
        with pytest.raises(IdentityServiceError):
            mod.base_url()

    def test_blank_is_treated_as_unset(self, monkeypatch):
        monkeypatch.setenv(mod.IDENTITY_SERVICE_URL_ENV, "   ")
        with pytest.raises(IdentityServiceError):
            mod.base_url()

    def test_trailing_slash_is_stripped(self, monkeypatch):
        monkeypatch.setenv(mod.IDENTITY_SERVICE_URL_ENV, "http://ident/")
        assert mod.base_url() == "http://ident"


@pytest.mark.unit
class TestForwardableHeaders:
    def test_keeps_only_credential_headers(self):
        got = forwardable_headers(
            {
                "Cookie": "_identityJwt=abc",
                "Authorization": "Bearer xyz",
                "X-Api-Key": "ssk_is_x",
                "X-Selected-Account-Id": "acct-1",
                "User-Agent": "curl",
                "Content-Length": "12",
            }
        )
        assert set(got) == {
            "cookie",
            "authorization",
            "x-api-key",
            "x-selected-account-id",
        }

    def test_drops_empty_values_and_is_case_insensitive(self):
        assert forwardable_headers({"COOKIE": "", "authorization": "Bearer z"}) == {
            "authorization": "Bearer z"
        }

    def test_nothing_to_forward_is_empty(self):
        assert forwardable_headers({"user-agent": "curl"}) == {}


@pytest.mark.unit
@pytest.mark.asyncio
class TestMint:
    async def test_sends_camelcase_fields_and_returns_the_secret(self, monkeypatch):
        captured: dict = {}
        expires = datetime(2026, 9, 30, tzinfo=UTC)
        _fake_http(
            monkeypatch,
            body={"id": "k1", "secret": _GOOD, "expiresOn": "2026-09-30T00:00:00Z"},
            captured=captured,
        )

        secret, expiry = await IdentityServiceClient("http://ident").mint_user_api_key(
            sgp_user_id=_USER,
            name="agentex-slack-link-U1",
            auth_headers={"cookie": "_identityJwt=abc"},
            expires_on=expires,
        )

        assert secret == _GOOD
        assert expiry == expires
        assert captured["url"] == "http://ident/api-keys"
        # camelCase — egp-api-backend's equivalent uses snake_case, and mixing them
        # up produces a 422 that reads like a server bug.
        assert captured["json"]["identityId"] == _USER
        assert captured["json"]["identityType"] == "user"
        assert "expiresOn" in captured["json"]
        # The caller's own session is forwarded, so the user mints their own key.
        assert captured["headers"]["cookie"] == "_identityJwt=abc"

    async def test_omits_expiry_when_not_requested(self, monkeypatch):
        captured: dict = {}
        _fake_http(monkeypatch, body={"secret": _GOOD}, captured=captured)
        await IdentityServiceClient("http://ident").mint_user_api_key(
            sgp_user_id=_USER, name="n", auth_headers={}
        )
        assert "expiresOn" not in captured["json"]

    async def test_falls_back_to_requested_expiry_when_response_omits_it(
        self, monkeypatch
    ):
        want = datetime.now(UTC) + timedelta(days=30)
        _fake_http(monkeypatch, body={"secret": _GOOD})
        _secret, expiry = await IdentityServiceClient("http://i").mint_user_api_key(
            sgp_user_id=_USER, name="n", auth_headers={}, expires_on=want
        )
        assert expiry == want


@pytest.mark.unit
@pytest.mark.asyncio
class TestMintFailures:
    async def test_rejects_a_non_ssk_key(self, monkeypatch):
        # THE important case: egp-api-backend mints sk_ keys that authenticate there
        # but 401 at sgp-secrets. Failing here beats debugging that later.
        _fake_http(monkeypatch, body={"secret": "sk_" + "b" * 100})
        with pytest.raises(IdentityServiceError, match="unexpected key format"):
            await IdentityServiceClient("http://i").mint_user_api_key(
                sgp_user_id=_USER, name="n", auth_headers={}
            )

    async def test_missing_secret_in_response(self, monkeypatch):
        _fake_http(monkeypatch, body={"id": "k1"})
        with pytest.raises(IdentityServiceError, match="no secret"):
            await IdentityServiceClient("http://i").mint_user_api_key(
                sgp_user_id=_USER, name="n", auth_headers={}
            )

    @pytest.mark.parametrize("status", [401, 403])
    async def test_auth_failure_asks_the_user_to_sign_in(self, monkeypatch, status):
        _fake_http(monkeypatch, status=status, body={})
        with pytest.raises(IdentityServiceError, match="session wasn't accepted"):
            await IdentityServiceClient("http://i").mint_user_api_key(
                sgp_user_id=_USER, name="n", auth_headers={}
            )

    @pytest.mark.parametrize("status", [422, 500])
    async def test_other_errors_surface_the_status(self, monkeypatch, status):
        _fake_http(monkeypatch, status=status, body={})
        with pytest.raises(IdentityServiceError, match=str(status)):
            await IdentityServiceClient("http://i").mint_user_api_key(
                sgp_user_id=_USER, name="n", auth_headers={}
            )

    async def test_network_failure_is_reported_not_swallowed(self, monkeypatch):
        _fake_http(monkeypatch, raises=OSError("dns"))
        with pytest.raises(IdentityServiceError, match="Couldn't reach"):
            await IdentityServiceClient("http://i").mint_user_api_key(
                sgp_user_id=_USER, name="n", auth_headers={}
            )

    async def test_refuses_without_a_user_id(self):
        with pytest.raises(IdentityServiceError, match="without a user id"):
            await IdentityServiceClient("http://i").mint_user_api_key(
                sgp_user_id="", name="n", auth_headers={}
            )
