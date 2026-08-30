"""Unit tests for the identity-link routes.

The credential stored here is the caller's own session cookie, so what needs testing
is mostly refusals: every path where we could end up storing something unusable, or
storing nothing while telling the user they're connected.

There is no minting to test. Minting was the original design and it cannot work —
identity-service permits one API key per user, every active user already has one, so
the create returns 409 and the existing key's secret can't be read back.
"""

import base64
import html
import json
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


def _jwt(exp: datetime | None) -> str:
    """A JWT-shaped token. Only the payload matters: nothing verifies the signature,
    and nothing should — see src/utils/session_jwt.py."""
    claims = {"sub": "abc"}
    if exp is not None:
        claims["exp"] = int(exp.timestamp())
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


_VALID_JWT = _jwt(datetime.now(UTC) + timedelta(days=150))


def _request(principal: dict | None, *, cookie: str | None = None):
    """Minimal Request stand-in: what the auth middleware would have populated.

    ``cookie`` defaults to a realistic browser header — the session cookie buried
    among unrelated morsels — because that is the case the parser has to survive.
    """
    if cookie is None:
        cookie = f"_ga=GA1.2.x; _identityJwt={_VALID_JWT}; __utmzz=(not set)"
    return SimpleNamespace(
        state=SimpleNamespace(principal_context=principal),
        headers={"cookie": cookie} if cookie else {},
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
    """Stub the two remaining collaborators: nonce store and repository."""
    nonce = MagicMock()
    nonce.peek = AsyncMock(return_value=_link_request())
    nonce.consume = AsyncMock(return_value=_link_request())
    monkeypatch.setattr(mod, "LinkNonceService", lambda *a, **k: nonce)

    repo = MagicMock()
    repo.get_active_by_sgp_user = AsyncMock(return_value=None)
    repo.upsert_link = AsyncMock(return_value=MagicMock(id="l1"))
    service = SimpleNamespace(repository=repo, invalidate=AsyncMock())
    monkeypatch.setattr(mod, "_identity_link_service", lambda: service)

    return SimpleNamespace(nonce=nonce, repo=repo, service=service)


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
    async def test_stores_the_callers_session_and_invalidates(self, wiring):
        resp = await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="tok")

        assert resp.status_code == 200
        assert "connected" in resp.body.decode().lower()

        stored = wiring.repo.upsert_link.await_args.kwargs
        assert stored["provider"] == IdentityProvider.SLACK
        assert stored["external_user_id"] == "U1"
        assert stored["sgp_user_id"] == _SGP_USER
        assert stored["linked_via"] == IdentityLinkMethod.EXPLICIT
        # The credential is the caller's own session cookie, pulled out of a
        # realistic Cookie header full of unrelated morsels.
        assert stored["credential"] == _VALID_JWT
        # The account has to be stored too: the secrets service refuses a session
        # credential without one, and it must be the user's own account.
        assert stored["sgp_account_id"] == "acct-1"

        # Negative cache dropped so the next Slack message resolves immediately.
        wiring.service.invalidate.assert_awaited_once()

    async def test_expiry_comes_from_the_token_not_a_guessed_ttl(self, wiring):
        await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="tok")
        stored = wiring.repo.upsert_link.await_args.kwargs["credential_expires_at"]
        # ~150 days out, from the JWT's own exp claim.
        assert 149 <= (stored - datetime.now(UTC)).days <= 150

    async def test_token_without_an_exp_gets_a_bounded_fallback(self, wiring):
        # Never store an unbounded credential: an unknown expiry becomes a short
        # known one rather than "valid forever".
        req = _request(_PRINCIPAL, cookie=f"_identityJwt={_jwt(None)}")
        resp = await mod.slack_link_confirm(req, nonce="tok")

        assert resp.status_code == 200
        stored = wiring.repo.upsert_link.await_args.kwargs["credential_expires_at"]
        assert stored is not None
        assert 0 < (stored - datetime.now(UTC)).days <= mod._FALLBACK_TTL_DAYS

    async def test_already_expired_token_is_refused(self, wiring):
        req = _request(
            _PRINCIPAL,
            cookie=f"_identityJwt={_jwt(datetime.now(UTC) - timedelta(minutes=1))}",
        )
        resp = await mod.slack_link_confirm(req, nonce="tok")

        assert resp.status_code == 401
        # Storing it would create a link that can never work.
        wiring.repo.upsert_link.assert_not_awaited()
        wiring.nonce.consume.assert_not_awaited()

    async def test_no_session_cookie_stores_nothing(self, wiring):
        # Authenticated by an api-key or bearer rather than a browser session: there
        # is nothing here we could act through later.
        req = _request(_PRINCIPAL, cookie="_ga=GA1.2.x; csrftoken=abc")
        resp = await mod.slack_link_confirm(req, nonce="tok")

        assert resp.status_code == 400
        wiring.repo.upsert_link.assert_not_awaited()
        wiring.nonce.consume.assert_not_awaited()

    async def test_principal_without_an_account_is_refused(self, wiring):
        # The secrets service requires account context, so a link without one would
        # look connected and resolve nothing.
        req = _request({**_PRINCIPAL, "account_id": None})
        resp = await mod.slack_link_confirm(req, nonce="tok")

        assert resp.status_code == 400
        assert "account" in resp.body.decode().lower()
        wiring.repo.upsert_link.assert_not_awaited()

    async def test_nonce_is_consumed_only_after_a_successful_store(self, wiring):
        await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="tok")
        wiring.nonce.consume.assert_awaited_once()

    async def test_expired_nonce_is_refused(self, wiring):
        wiring.nonce.peek = AsyncMock(return_value=None)
        resp = await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="stale")
        assert resp.status_code == 400
        wiring.repo.upsert_link.assert_not_awaited()

    async def test_unauthenticated_stores_nothing(self, wiring):
        resp = await mod.slack_link_confirm(_request(None), nonce="tok")
        assert resp.status_code == 401
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
        wiring.repo.upsert_link.assert_not_awaited()

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
        # If AGENTEX_CREDENTIAL_ENCRYPTION_KEY is missing, the session credential
        # cannot be stored safely. It must NOT be persisted in plaintext, and the
        # user should see an operator problem rather than an opaque error they'd
        # retry forever.
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


@pytest.mark.unit
@pytest.mark.asyncio
class TestEmailMatch:
    """The self-enabling defence against a *forwarded* link.

    The nonce stops an attacker forging someone else's Slack identity. It does not
    stop them sending their OWN link to a victim: clicking it while signed in binds
    the attacker's Slack identity to the victim's SGP account, and from then on the
    attacker's Slack messages run as the victim with the victim's integrations.
    Comparing the two accounts' emails is what closes that.

    There is deliberately no flag. The check needs the `users:read.email` Slack
    scope, and gating it on config means the flag and the scope must be flipped
    together — flipping one alone either refuses every link or silently protects
    nothing. Instead it enforces whenever Slack answers with an email and stands
    down when it won't, so granting the scope turns the protection on by itself.

    The asymmetry that follows is the thing to pin: **verified different -> refuse,
    unverifiable -> allow**.
    """

    def _slack_profile(self, monkeypatch, **profile):
        import src.domain.use_cases.slack_gateway_use_case as sg

        full = {"display_name": "@x", "email": None, "error": None, **profile}
        probe = AsyncMock(return_value=full)
        monkeypatch.setattr(sg, "slack_user_profile", probe)
        return probe

    async def test_matching_emails_link_successfully(self, wiring, monkeypatch):
        self._slack_profile(monkeypatch, email=_SGP_EMAIL)
        resp = await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="tok")
        assert resp.status_code == 200
        wiring.repo.upsert_link.assert_awaited_once()

    async def test_match_ignores_case_and_surrounding_space(self, wiring, monkeypatch):
        self._slack_profile(monkeypatch, email=f"  {_SGP_EMAIL.upper()} ")
        resp = await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="tok")
        assert resp.status_code == 200

    async def test_mismatch_is_refused_and_stores_nothing(self, wiring, monkeypatch):
        self._slack_profile(monkeypatch, email="attacker@example.com")

        resp = await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="tok")

        assert resp.status_code == 403
        wiring.repo.upsert_link.assert_not_awaited()
        # The nonce survives a refusal, so the link's legitimate owner can still use
        # it — refusing the wrong clicker must not burn the right one's link.
        wiring.nonce.consume.assert_not_awaited()
        body = resp.body.decode().lower()
        assert "don&#x27;t use it" in body or "don't use it" in body

    async def test_missing_scope_allows_the_link(self, wiring, monkeypatch):
        # The current production state: users:read.email isn't granted, so Slack
        # won't tell us. Refusing here would block every link in the workspace, so
        # the check stands down rather than failing closed.
        self._slack_profile(monkeypatch, email=None, error="missing_scope")
        resp = await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="tok")
        assert resp.status_code == 200
        wiring.repo.upsert_link.assert_awaited_once()

    async def test_lookup_failure_allows_the_link(self, wiring, monkeypatch):
        # Same rule for a transient failure. Failing closed on an unreadable email
        # would make linking fail randomly, and the gap isn't attacker-reachable:
        # nobody outside our infrastructure decides whether our Slack call succeeds.
        self._slack_profile(monkeypatch, email=None, error="request_failed")
        resp = await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="tok")
        assert resp.status_code == 200

    async def test_missing_sgp_email_allows_the_link(self, wiring, monkeypatch):
        # Slack told us, but the SGP principal carries no email: nothing to compare
        # against, so the same "can't verify, don't block" rule applies.
        self._slack_profile(monkeypatch, email="someone@example.com")
        resp = await mod.slack_link_confirm(
            _request({**_PRINCIPAL, "raw_user": {}}), nonce="tok"
        )
        assert resp.status_code == 200

    async def test_the_check_runs_on_every_confirm(self, wiring, monkeypatch):
        # No flag means no way to accidentally leave it off: granting the scope is
        # the only thing standing between here and enforcement.
        probe = self._slack_profile(monkeypatch, email=_SGP_EMAIL)
        await mod.slack_link_confirm(_request(_PRINCIPAL), nonce="tok")
        probe.assert_awaited_once()
        assert probe.await_args.args[0] == "U1"


@pytest.mark.unit
@pytest.mark.asyncio
class TestNoRawIdentifiersOnThePage:
    """The confirmation page never prints an internal id.

    The identity rows exist so someone can answer "is this *my* account?". Nobody
    recognises their own Slack `U…` id or SGP uuid, so falling back to one doesn't
    make the check possible — it exposes an internal identifier while making an
    unanswerable question look answered.
    """

    def _no_slack_lookup(self, monkeypatch, name=None):
        import src.domain.use_cases.slack_gateway_use_case as sg

        monkeypatch.setattr(
            sg, "slack_user_profile", AsyncMock(return_value={"display_name": name})
        )

    async def test_named_identities_are_shown(self, wiring, monkeypatch):
        self._no_slack_lookup(monkeypatch)
        body = (
            await mod.slack_link_page(_request(_PRINCIPAL), nonce="tok")
        ).body.decode()
        assert _SLACK_HANDLE in body and _SGP_EMAIL in body

    async def test_missing_slack_name_does_not_fall_back_to_the_member_id(
        self, wiring, monkeypatch
    ):
        wiring.nonce.peek = AsyncMock(return_value=_link_request(display_name=""))
        self._no_slack_lookup(monkeypatch)  # live lookup also comes back empty

        body = (
            await mod.slack_link_page(_request(_PRINCIPAL), nonce="tok")
        ).body.decode()

        assert "U1" not in body
        assert html.escape(mod._UNKNOWN_IDENTITY) in body

    async def test_missing_slack_name_is_re_read_live(self, wiring, monkeypatch):
        # A transient Slack failure when the nonce was minted shouldn't permanently
        # degrade the page — users:read is enough to recover the handle.
        wiring.nonce.peek = AsyncMock(return_value=_link_request(display_name=""))
        self._no_slack_lookup(monkeypatch, name="@recovered")

        body = (
            await mod.slack_link_page(_request(_PRINCIPAL), nonce="tok")
        ).body.decode()
        assert "@recovered" in body

    async def test_missing_email_does_not_fall_back_to_the_uuid(
        self, wiring, monkeypatch
    ):
        self._no_slack_lookup(monkeypatch)
        body = (
            await mod.slack_link_page(
                _request({**_PRINCIPAL, "raw_user": {}}), nonce="tok"
            )
        ).body.decode()

        assert _SGP_USER not in body
        assert html.escape(mod._UNKNOWN_IDENTITY) in body

    async def test_unnamed_identity_says_the_check_is_unavailable(
        self, wiring, monkeypatch
    ):
        # Don't imply someone verified a match they had no way to verify.
        self._no_slack_lookup(monkeypatch)
        body = (
            await mod.slack_link_page(
                _request({**_PRINCIPAL, "raw_user": {}}), nonce="tok"
            )
        ).body.decode()
        assert "couldn&#x27;t be identified" in body or "couldn't be identified" in body

    async def test_success_page_does_not_print_the_uuid(self, wiring, monkeypatch):
        self._no_slack_lookup(monkeypatch)
        resp = await mod.slack_link_confirm(
            _request({**_PRINCIPAL, "raw_user": {}}), nonce="tok"
        )
        assert resp.status_code == 200
        assert _SGP_USER not in resp.body.decode()


@pytest.mark.unit
class TestMultiNameCookieAllowlist:
    """A session may arrive under ANY allowlisted cookie name.

    REGRESSION: this used to read only the first entry of
    AGENTEX_DELEGATION_SESSION_COOKIE_NAMES. With a multi-name allowlist, a session
    carried by a later name was rejected — linking failed with "couldn't read your
    session" for a cookie the delegation layer would have forwarded quite happily.
    The allowlist is a set of names the deployment treats as valid, so second is as
    legitimate as first.
    """

    def _request(self, cookie: str):
        return SimpleNamespace(headers={"cookie": cookie})

    def _allow(self, monkeypatch, names: str):
        from src.domain.delegation_headers import ENV_SESSION_COOKIE_NAMES

        monkeypatch.setenv(ENV_SESSION_COOKIE_NAMES, names)

    def test_session_under_a_later_name_is_accepted(self, monkeypatch):
        self._allow(monkeypatch, "_identityJwt,_jwt")
        assert mod._session_credential(self._request("_jwt=BBB")) == "BBB"

    def test_allowlist_order_wins_when_several_are_present(self, monkeypatch):
        # Deterministic, and prefers the deployment's canonical cookie — which is
        # also the name acting_headers() emits under.
        self._allow(monkeypatch, "_identityJwt,_jwt")
        got = mod._session_credential(self._request("_jwt=BBB; _identityJwt=AAA"))
        assert got == "AAA"

    def test_later_name_survives_a_messy_browser_header(self, monkeypatch):
        self._allow(monkeypatch, "_identityJwt,_jwt")
        cookie = "_ga=GA1.2.x; __utmzz=(not set); _jwt=BBB; fs_uid=a#b"
        assert mod._session_credential(self._request(cookie)) == "BBB"

    def test_names_outside_the_allowlist_are_still_rejected(self, monkeypatch):
        # Widening to "any cookie that looks like a session" would let an attacker
        # nominate the credential we store.
        self._allow(monkeypatch, "_identityJwt")
        assert mod._session_credential(self._request("_jwt=BBB")) is None

    def test_empty_allowlist_reads_nothing(self, monkeypatch):
        self._allow(monkeypatch, "")
        assert mod._session_credential(self._request("_identityJwt=AAA")) is None

    def test_blank_value_is_not_a_session(self, monkeypatch):
        self._allow(monkeypatch, "_identityJwt,_jwt")
        assert (
            mod._session_credential(self._request("_identityJwt=; _jwt=BBB")) == "BBB"
        )

    def test_emitted_name_stays_canonical(self, monkeypatch):
        # Reading accepts many; writing must choose one. The stored value is a JWT
        # validated on its contents, not on the label it travels under.
        from src.domain.services.identity_link_service import (
            session_cookie_name,
            session_cookie_names,
        )

        self._allow(monkeypatch, "_identityJwt,_jwt")
        assert session_cookie_names() == ("_identityJwt", "_jwt")
        assert session_cookie_name() == "_identityJwt"
