"""Unit tests for the identity-link routes.

Covers everything that doesn't require a real browser session: nonce handling, the
unauthenticated path, conflict detection, mint-failure behavior, and the ordering
guarantee that a failed mint doesn't burn the user's link.

What these can NOT cover, and why: ``POST /api-keys`` on identity-service is guarded
by ``CustomerIdentityJwtGuard``, which reads ``_identityJwt`` / ``_jwt`` cookies and
rejects ``x-api-key``. So the live mint needs a genuine browser session and is
exercised via scripts/dev_seed_link_nonce.py against a deployed host, not here.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.api.routes import integrations as mod
from src.domain.entities.identity_links import IdentityLinkMethod, IdentityProvider
from src.domain.services.link_nonce_service import LinkRequest

_SGP_USER = "11111111-2222-4333-8444-555555555555"
_SGP_EMAIL = "test.user@example.com"
_SLACK_HANDLE = "@test.user"
_GOOD_KEY = "ssk_is_" + "a" * 32


def _request(principal: dict | None):
    """Minimal Request stand-in: what the auth middleware would have populated."""
    return SimpleNamespace(
        state=SimpleNamespace(principal_context=principal),
        headers={"cookie": "_identityJwt=abc"},
    )


def _link_request(**kw) -> LinkRequest:
    return LinkRequest(
        **{
            "provider": "slack",
            "external_team_id": "T1",
            "external_user_id": "U1",
            "display_name": _SLACK_HANDLE,
            "pending_turn": {"text": "hi"},
            **kw,
        }
    )


_PRINCIPAL = {
    "user_id": _SGP_USER,
    "account_id": "acct-1",
    "raw_user": {"email": _SGP_EMAIL},
}


@pytest.fixture
def wiring(monkeypatch):
    """Stub the three collaborators: nonce store, repository, identity-service."""
    nonce = MagicMock()
    nonce.peek = AsyncMock(return_value=_link_request())
    nonce.consume = AsyncMock(return_value=_link_request())
    monkeypatch.setattr(mod, "LinkNonceService", lambda *a, **k: nonce)

    repo = MagicMock()
    repo.get_active_by_sgp_user = AsyncMock(return_value=None)
    repo.upsert_link = AsyncMock(return_value=MagicMock(id="l1"))
    service = SimpleNamespace(repository=repo, invalidate=AsyncMock())
    monkeypatch.setattr(mod, "_identity_link_service", lambda: service)

    client = MagicMock()
    client.mint_user_api_key = AsyncMock(
        return_value=(_GOOD_KEY, datetime.now(UTC) + timedelta(days=30))
    )
    monkeypatch.setattr(mod, "IdentityServiceClient", lambda *a, **k: client)

    return SimpleNamespace(nonce=nonce, repo=repo, service=service, client=client)


@pytest.mark.unit
@pytest.mark.asyncio
class TestConfirmationPage:
    async def test_names_both_identities(self, wiring):
        resp = await mod.slack_link_page(_request(_PRINCIPAL), nonce="tok")
        body = resp.body.decode()
        assert resp.status_code == 200
        # Naming both sides is the security control: it's what makes a mis-clicked
        # link visible to whoever clicked it.
        assert _SLACK_HANDLE in body
        assert _SGP_EMAIL in body
        assert "isn&#x27;t you" in body or "isn't you" in body

    async def test_does_not_consume_the_nonce(self, wiring):
        await mod.slack_link_page(_request(_PRINCIPAL), nonce="tok")
        wiring.nonce.consume.assert_not_awaited()

    async def test_expired_nonce_says_so(self, wiring):
        wiring.nonce.peek = AsyncMock(return_value=None)
        resp = await mod.slack_link_page(_request(_PRINCIPAL), nonce="stale")
        assert resp.status_code == 400
        assert "expired" in resp.body.decode().lower()

    async def test_unauthenticated_asks_for_sign_in(self, wiring):
        resp = await mod.slack_link_page(_request(None), nonce="tok")
        assert resp.status_code == 401
        assert "sign in" in resp.body.decode().lower()

    async def test_display_name_is_html_escaped(self, wiring):
        wiring.nonce.peek = AsyncMock(
            return_value=_link_request(display_name="<script>alert(1)</script>")
        )
        body = (
            await mod.slack_link_page(_request(_PRINCIPAL), nonce="t")
        ).body.decode()
        assert "<script>" not in body
        assert "&lt;script&gt;" in body


@pytest.mark.unit
@pytest.mark.asyncio
class TestConfirm:
    async def test_mints_stores_and_invalidates(self, wiring):
        resp = await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="tok")

        assert resp.status_code == 200
        assert "connected" in resp.body.decode().lower()

        # Minted as the signed-in user, with an expiry.
        mint = wiring.client.mint_user_api_key.await_args.kwargs
        assert mint["sgp_user_id"] == _SGP_USER
        assert mint["expires_on"] is not None
        # The caller's cookie is forwarded — an api-key can't satisfy the guard.
        assert mint["auth_headers"].get("cookie") == "_identityJwt=abc"

        # Stored against the Slack identity from the nonce, with the credential.
        stored = wiring.repo.upsert_link.await_args.kwargs
        assert stored["provider"] == IdentityProvider.SLACK
        assert stored["external_user_id"] == "U1"
        assert stored["sgp_user_id"] == _SGP_USER
        assert stored["credential"] == _GOOD_KEY
        assert stored["linked_via"] == IdentityLinkMethod.EXPLICIT

        # Negative cache dropped so the next Slack message resolves immediately.
        wiring.service.invalidate.assert_awaited_once()

    async def test_nonce_is_consumed_only_after_a_successful_store(self, wiring):
        await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="tok")
        wiring.nonce.consume.assert_awaited_once()

    async def test_failed_mint_leaves_the_link_usable(self, wiring):
        # A transient identity-service failure must not burn the nonce, or the user
        # has to go back to Slack to get a new link for no reason.
        wiring.client.mint_user_api_key = AsyncMock(
            side_effect=mod.IdentityServiceError("service down")
        )
        resp = await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="tok")

        assert resp.status_code == 502
        wiring.nonce.consume.assert_not_awaited()
        wiring.repo.upsert_link.assert_not_awaited()
        assert "still valid" in resp.body.decode()

    async def test_expired_nonce_is_refused(self, wiring):
        wiring.nonce.peek = AsyncMock(return_value=None)
        resp = await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="stale")
        assert resp.status_code == 400
        wiring.client.mint_user_api_key.assert_not_awaited()

    async def test_unauthenticated_mints_nothing(self, wiring):
        resp = await mod.slack_link_confirm(_request(None), nonce="tok")
        assert resp.status_code == 401
        wiring.client.mint_user_api_key.assert_not_awaited()
        wiring.repo.upsert_link.assert_not_awaited()

    async def test_sgp_account_already_linked_to_another_slack_user(self, wiring):
        # Reported before the partial unique index would reject it, so the user
        # gets a sentence instead of an integrity error.
        wiring.repo.get_active_by_sgp_user = AsyncMock(
            return_value=SimpleNamespace(external_user_id="U-someone-else")
        )
        resp = await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="tok")

        assert resp.status_code == 409
        assert "already linked" in resp.body.decode().lower()
        wiring.client.mint_user_api_key.assert_not_awaited()

    async def test_relinking_the_same_slack_user_is_allowed(self, wiring):
        # Same identity re-linking (e.g. after expiry) must go through — it's the
        # documented recovery path.
        wiring.repo.get_active_by_sgp_user = AsyncMock(
            return_value=SimpleNamespace(external_user_id="U1")
        )
        resp = await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="tok")
        assert resp.status_code == 200
        wiring.repo.upsert_link.assert_awaited_once()

    async def test_unconfigured_encryption_key_is_reported_not_a_500(self, wiring):
        # If AGENTEX_CREDENTIAL_ENCRYPTION_KEY is missing, the minted key cannot be
        # stored safely. It must NOT be persisted in plaintext, and the user should
        # see an operator problem rather than an opaque error they'd retry forever.
        wiring.repo.upsert_link = AsyncMock(
            side_effect=mod.CredentialEncryptionError("key unset")
        )
        resp = await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="tok")

        assert resp.status_code == 503
        assert (
            "isn&#x27;t set up" in resp.body.decode()
            or "isn't set up" in resp.body.decode()
        )
        # Nonce preserved so the link works once the key is configured.
        wiring.nonce.consume.assert_not_awaited()
