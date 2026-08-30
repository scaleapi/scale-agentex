"""Unit tests for IdentityLinkService.

Two properties matter most here, and both are about not lying:

1. "Unlinked" and "lookup failed" must never be confused. The caller treats the
   first as "run as the shared bot", so collapsing a database error into it would
   silently downgrade a user-scoped turn.
2. ``acting_headers`` must return None — not a partial or stale credential — for
   every reason it can't act as someone, because the alternative is sending a
   wrong key to SGP.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.domain.entities.identity_links import (
    IdentityLinkEntity,
    IdentityLinkMethod,
    IdentityProvider,
)
from src.domain.services import identity_link_service as mod
from src.domain.services.identity_link_service import (
    IdentityLinkService,
    ResolvedIdentity,
)
from src.utils.credential_encryption import CredentialEncryptionError


def _link(**kw) -> IdentityLinkEntity:
    return IdentityLinkEntity(
        **{
            "id": "l1",
            "provider": IdentityProvider.SLACK,
            "external_team_id": "T1",
            "external_user_id": "U1",
            "sgp_user_id": "sgp-user-1",
            "sgp_account_id": "acct-1",
            "linked_via": IdentityLinkMethod.EXPLICIT,
            "has_credential": True,
            "credential_expires_at": datetime.now(UTC) + timedelta(days=30),
            "linked_at": datetime(2026, 8, 25, tzinfo=UTC),
            "revoked_at": None,
            **kw,
        }
    )


def _service(link=None, *, credential="ssk_is_key", repo=None):
    repository = repo or MagicMock()
    if repo is None:
        repository.get_active_by_external_user = AsyncMock(return_value=link)
        repository.get_credential = AsyncMock(return_value=credential)
    return IdentityLinkService(repository), repository


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch):
    """Default: no cache. Tests that care install a fake."""
    monkeypatch.setattr(IdentityLinkService, "_redis", lambda self: None)


@pytest.mark.unit
@pytest.mark.asyncio
class TestResolve:
    async def test_linked_user_resolves_with_a_credential_free_principal(self):
        service, _ = _service(_link())
        identity = await service.resolve(IdentityProvider.SLACK, "T1", "U1")
        assert identity is not None
        # Authorization needs only (user_id, account_id); the key travels separately.
        assert identity.principal == {"user_id": "sgp-user-1", "account_id": "acct-1"}
        assert "api_key" not in identity.principal

    async def test_unlinked_user_resolves_to_none(self):
        service, _ = _service(None)
        assert await service.resolve(IdentityProvider.SLACK, "T1", "U-nope") is None

    async def test_lookup_failure_raises_rather_than_reporting_unlinked(self):
        repo = MagicMock()
        repo.get_active_by_external_user = AsyncMock(side_effect=OSError("db down"))
        service, _ = _service(repo=repo)
        with pytest.raises(OSError):
            await service.resolve(IdentityProvider.SLACK, "T1", "U1")

    @pytest.mark.parametrize("team, user", [("", "U1"), ("T1", ""), ("", "")])
    async def test_missing_identity_parts_short_circuit(self, team, user):
        service, repo = _service(_link())
        assert await service.resolve(IdentityProvider.SLACK, team, user) is None
        repo.get_active_by_external_user.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
class TestActingHeaders:
    async def test_happy_path_returns_the_users_session_and_account(self):
        service, _ = _service(_link(), credential="jwt.header.sig")
        identity = ResolvedIdentity(_link())

        headers = await service.acting_headers(identity)

        # This exact shape is what becomes x-acting-user-cookie downstream, which is
        # what makes the secrets service return THIS user's Notion token. The cookie
        # name has to match the delegation allowlist or it's dropped en route.
        assert headers == {
            "cookie": "_identityJwt=jwt.header.sig",
            "x-selected-account-id": "acct-1",
        }

    async def test_missing_account_id_returns_none(self):
        # The secrets service refuses a session credential with no account context,
        # so a link lacking one cannot be acted through. Returning partial headers
        # would produce a confusing downstream 400 instead of a clean fallback.
        service, _ = _service(_link(sgp_account_id=""), credential="jwt.a.b")
        identity = ResolvedIdentity(_link(sgp_account_id=""))
        assert await service.acting_headers(identity) is None

    async def test_link_without_a_credential_returns_none(self):
        service, repo = _service(_link(has_credential=False))
        identity = ResolvedIdentity(_link(has_credential=False))
        assert await service.acting_headers(identity) is None
        repo.get_credential.assert_not_awaited()  # no pointless DB read

    async def test_expired_credential_returns_none_without_reading_it(self):
        expired = _link(credential_expires_at=datetime.now(UTC) - timedelta(minutes=1))
        service, repo = _service(expired)
        assert await service.acting_headers(ResolvedIdentity(expired)) is None
        # Expiry is checked locally, so an expired key is never even decrypted.
        repo.get_credential.assert_not_awaited()

    async def test_credential_with_no_expiry_is_treated_as_valid(self):
        forever = _link(credential_expires_at=None)
        service, _ = _service(forever, credential="jwt.forever.sig")
        headers = await service.acting_headers(ResolvedIdentity(forever))
        assert headers["cookie"] == "_identityJwt=jwt.forever.sig"

    async def test_undecryptable_credential_returns_none_not_an_exception(self):
        # A rotated encryption key leaves existing rows unreadable. That must
        # surface as "can't act as them" so the turn falls back or prompts a
        # re-link — not as a 500.
        repo = MagicMock()
        repo.get_credential = AsyncMock(
            side_effect=CredentialEncryptionError("different key")
        )
        service, _ = _service(repo=repo)
        assert await service.acting_headers(ResolvedIdentity(_link())) is None

    async def test_revoked_link_is_not_usable(self):
        revoked = _link(revoked_at=datetime.now(UTC))
        service, repo = _service(revoked)
        assert await service.acting_headers(ResolvedIdentity(revoked)) is None
        repo.get_credential.assert_not_awaited()

    async def test_empty_stored_credential_returns_none(self):
        service, _ = _service(_link(), credential="")
        assert await service.acting_headers(ResolvedIdentity(_link())) is None


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value
        self.ttls[key] = ex

    async def delete(self, key):
        self.store.pop(key, None)


@pytest.mark.unit
@pytest.mark.asyncio
class TestCaching:
    @staticmethod
    def _with_cache(monkeypatch, service):
        fake = _FakeRedis()
        monkeypatch.setattr(type(service), "_redis", lambda self: fake)
        return fake

    async def test_second_resolve_is_served_from_cache(self, monkeypatch):
        service, repo = _service(_link())
        self._with_cache(monkeypatch, service)
        await service.resolve(IdentityProvider.SLACK, "T1", "U1")
        await service.resolve(IdentityProvider.SLACK, "T1", "U1")
        repo.get_active_by_external_user.assert_awaited_once()

    async def test_the_cached_payload_contains_no_credential(self, monkeypatch):
        # The whole reason caching the link is safe: the entity has no key on it.
        service, _ = _service(_link())
        fake = self._with_cache(monkeypatch, service)
        await service.resolve(IdentityProvider.SLACK, "T1", "U1")
        payload = fake.store["identity_link:slack:T1:U1"]
        assert "ssk_" not in payload
        assert "credential_ciphertext" not in payload
        assert '"has_credential":true' in payload.replace(" ", "")

    async def test_unlinked_result_is_cached_negatively(self, monkeypatch):
        service, repo = _service(None)
        fake = self._with_cache(monkeypatch, service)
        assert await service.resolve(IdentityProvider.SLACK, "T1", "U1") is None
        assert await service.resolve(IdentityProvider.SLACK, "T1", "U1") is None
        repo.get_active_by_external_user.assert_awaited_once()
        assert fake.store["identity_link:slack:T1:U1"] == mod._UNLINKED

    async def test_negative_ttl_is_shorter_than_positive(self, monkeypatch):
        linked, _ = _service(_link())
        c1 = self._with_cache(monkeypatch, linked)
        await linked.resolve(IdentityProvider.SLACK, "T1", "U1")
        unlinked, _ = _service(None)
        c2 = self._with_cache(monkeypatch, unlinked)
        await unlinked.resolve(IdentityProvider.SLACK, "T1", "U2")
        assert (
            c2.ttls["identity_link:slack:T1:U2"] < c1.ttls["identity_link:slack:T1:U1"]
        )

    async def test_cache_failure_falls_through_to_the_database(self, monkeypatch):
        service, repo = _service(_link())
        broken = MagicMock()
        broken.get = AsyncMock(side_effect=OSError("redis gone"))
        broken.set = AsyncMock()
        monkeypatch.setattr(type(service), "_redis", lambda self: broken)
        assert await service.resolve(IdentityProvider.SLACK, "T1", "U1") is not None
        repo.get_active_by_external_user.assert_awaited_once()

    async def test_invalidate_forces_a_fresh_read(self, monkeypatch):
        service, repo = _service(_link())
        self._with_cache(monkeypatch, service)
        await service.resolve(IdentityProvider.SLACK, "T1", "U1")
        await service.invalidate(IdentityProvider.SLACK, "T1", "U1")
        await service.resolve(IdentityProvider.SLACK, "T1", "U1")
        assert repo.get_active_by_external_user.await_count == 2

    async def test_no_redis_pool_is_database_only(self, monkeypatch):
        service, repo = _service(_link())
        monkeypatch.setattr(
            mod,
            "GlobalDependencies",
            MagicMock(return_value=SimpleNamespace(redis_pool=None)),
            raising=False,
        )
        monkeypatch.setattr(type(service), "_redis", IdentityLinkService._redis)
        assert await service.resolve(IdentityProvider.SLACK, "T1", "U1") is not None
        repo.get_active_by_external_user.assert_awaited_once()


@pytest.mark.unit
class TestSessionCookieName:
    """The cookie name has exactly one source of truth.

    It used to be separately configurable here AND in delegation_headers. If the two
    diverged, acting_headers() would emit a Cookie header under a name the delegation
    allowlist filters out — the agent would get no acting credential at all, silently,
    while the link itself looked stored, valid and healthy. Deriving it removes the
    possibility rather than documenting it.
    """

    def test_follows_the_delegation_allowlist(self, monkeypatch):
        from src.domain.delegation_headers import ENV_SESSION_COOKIE_NAMES
        from src.domain.services.identity_link_service import session_cookie_name

        monkeypatch.setenv(ENV_SESSION_COOKIE_NAMES, "_sgpSession")
        assert session_cookie_name() == "_sgpSession"

    def test_defaults_with_the_delegation_module(self, monkeypatch):
        from src.domain.delegation_headers import ENV_SESSION_COOKIE_NAMES
        from src.domain.services.identity_link_service import session_cookie_name

        monkeypatch.delenv(ENV_SESSION_COOKIE_NAMES, raising=False)
        assert session_cookie_name() == "_identityJwt"

    def test_none_when_cookie_delegation_is_disabled(self, monkeypatch):
        from src.domain.delegation_headers import ENV_SESSION_COOKIE_NAMES
        from src.domain.services.identity_link_service import session_cookie_name

        monkeypatch.setenv(ENV_SESSION_COOKIE_NAMES, "")
        assert session_cookie_name() is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestActingHeadersFollowDelegation:
    async def test_emitted_cookie_survives_the_delegation_filter(self, monkeypatch):
        """The end-to-end property: whatever name is configured, what acting_headers
        emits is what build_delegation_headers forwards."""
        from src.domain.delegation_headers import (
            ENV_SESSION_COOKIE_NAMES,
            build_delegation_headers,
        )

        monkeypatch.setenv(ENV_SESSION_COOKIE_NAMES, "_sgpSession")
        service, _ = _service(_link(), credential="jwt.value.sig")

        headers = await service.acting_headers(ResolvedIdentity(_link()))
        assert headers["cookie"] == "_sgpSession=jwt.value.sig"

        forwarded = build_delegation_headers({"user_id": "u"}, dict(headers))
        # Not dropped in transit — the whole point of deriving the name.
        assert forwarded["x-acting-user-cookie"] == "_sgpSession=jwt.value.sig"

    async def test_refuses_when_cookie_delegation_is_disabled(self, monkeypatch):
        # Emitting a credential the delegation layer will strip would look like a
        # working link and deliver nothing, so refuse instead.
        from src.domain.delegation_headers import ENV_SESSION_COOKIE_NAMES

        monkeypatch.setenv(ENV_SESSION_COOKIE_NAMES, "")
        service, _ = _service(_link(), credential="jwt.value.sig")
        assert await service.acting_headers(ResolvedIdentity(_link())) is None
