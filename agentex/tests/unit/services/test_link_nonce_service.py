"""Unit tests for the link nonce.

The nonce exists to stop one specific attack: if the Slack identity travelled in the
URL, someone could bind *your* Slack account to *their* SGP account by editing a
query parameter. So the properties under test are about the token being opaque,
single-use, and carrying its payload server-side.
"""

import json

import pytest
from src.domain.services import link_nonce_service as mod
from src.domain.services.link_nonce_service import LinkNonceService, LinkRequest


class _FakeRedis:
    """Enough Redis for the nonce: get/set/getdel/delete/incr/expire/ttl."""

    def __init__(self, *, supports_getdel=True, supports_keepttl=True):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.supports_getdel = supports_getdel
        self.supports_keepttl = supports_keepttl

    async def set(self, key, value, ex=None, keepttl=False):
        if keepttl and not self.supports_keepttl:
            raise AttributeError("KEEPTTL unsupported")
        self.store[key] = value
        if not keepttl:
            self.ttls[key] = ex

    async def get(self, key):
        return self.store.get(key)

    async def getdel(self, key):
        if not self.supports_getdel:
            raise AttributeError("GETDEL unsupported")
        self.ttls.pop(key, None)
        return self.store.pop(key, None)

    async def delete(self, key):
        self.ttls.pop(key, None)
        self.store.pop(key, None)

    async def incr(self, key):
        nxt = int(self.store.get(key, 0)) + 1
        self.store[key] = str(nxt)
        return nxt

    async def expire(self, key, ttl):
        self.ttls[key] = ttl

    async def ttl(self, key):
        # Redis semantics: -1 when the key exists with no expiry.
        return self.ttls.get(key) if self.ttls.get(key) is not None else -1


def _req(**kw) -> LinkRequest:
    return LinkRequest(
        **{
            "provider": "slack",
            "external_team_id": "T1",
            "external_user_id": "U1",
            "display_name": "@test.user",
            "pending_turn": {"text": "what's in my notion?"},
            **kw,
        }
    )


@pytest.fixture
def svc():
    fake = _FakeRedis()
    return LinkNonceService(redis_client=fake), fake


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreate:
    async def test_token_is_opaque_and_carries_nothing_identifying(self, svc):
        service, _ = svc
        token = await service.create(_req())
        # Nothing about the Slack identity may be recoverable from the token itself,
        # or an attacker could craft one for a different user.
        for leak in ("T1", "U1", "slack", "test.user"):
            assert leak not in token

    async def test_tokens_are_unique(self, svc):
        service, _ = svc
        tokens = {await service.create(_req()) for _ in range(20)}
        assert len(tokens) == 20

    async def test_payload_is_stored_server_side_with_a_ttl(self, svc):
        service, fake = svc
        token = await service.create(_req())
        stored = json.loads(fake.store[f"link_nonce:{token}"])
        assert stored["external_user_id"] == "U1"
        assert stored["pending_turn"]["text"] == "what's in my notion?"
        assert fake.ttls[f"link_nonce:{token}"] == mod._TTL_S


@pytest.mark.unit
@pytest.mark.asyncio
class TestPeekAndConsume:
    async def test_peek_returns_the_request_without_consuming(self, svc):
        service, _ = svc
        token = await service.create(_req())
        # The confirmation page renders on GET; burning the nonce there would break
        # a refresh or a link-prefetching browser before the user could confirm.
        assert (await service.peek(token)).external_user_id == "U1"
        assert (await service.peek(token)).external_user_id == "U1"

    async def test_consume_returns_then_invalidates(self, svc):
        service, _ = svc
        token = await service.create(_req())
        assert (await service.consume(token)) is not None
        assert (await service.consume(token)) is None

    async def test_a_leaked_link_works_at_most_once(self, svc):
        service, _ = svc
        token = await service.create(_req())
        first = await service.consume(token)
        second = await service.consume(token)
        assert first is not None and second is None

    async def test_pending_turn_survives_the_round_trip(self, svc):
        service, _ = svc
        token = await service.create(
            _req(pending_turn={"text": "hi", "thread_ts": "1"})
        )
        got = await service.consume(token)
        assert got.pending_turn == {"text": "hi", "thread_ts": "1"}

    async def test_link_without_a_pending_turn_is_fine(self, svc):
        service, _ = svc
        token = await service.create(_req(pending_turn=None))
        assert (await service.consume(token)).pending_turn is None

    @pytest.mark.parametrize("token", ["", "not-a-real-token"])
    async def test_unknown_or_empty_token_is_none(self, svc, token):
        service, _ = svc
        assert await service.peek(token) is None
        assert await service.consume(token) is None

    async def test_malformed_payload_is_treated_as_expired(self, svc):
        service, fake = svc
        fake.store["link_nonce:broken"] = "{not json"
        assert await service.peek("broken") is None

    async def test_consume_falls_back_when_getdel_is_unsupported(self):
        # Redis < 6.2 has no GETDEL; the flow must still be single-use.
        fake = _FakeRedis(supports_getdel=False)
        service = LinkNonceService(redis_client=fake)
        token = await service.create(_req())
        assert (await service.consume(token)) is not None
        assert (await service.consume(token)) is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestOneLiveNoncePerIdentity:
    """A nonce is a bearer token, so a user must never hold several at once."""

    async def test_creating_again_invalidates_the_previous_link(self, svc):
        service, _ = svc
        first = await service.create(_req())
        second = await service.create(_req())
        assert first != second
        # The old link must be dead: otherwise ignoring a link and asking again
        # leaves two separately-redeemable tokens for the same identity, and
        # consuming one would not invalidate the other.
        assert await service.peek(first) is None
        assert await service.peek(second) is not None

    async def test_a_superseded_token_cannot_be_consumed(self, svc):
        service, _ = svc
        first = await service.create(_req())
        await service.create(_req())
        assert await service.consume(first) is None

    async def test_separate_identities_do_not_interfere(self, svc):
        service, _ = svc
        a = await service.create(_req(external_user_id="U1"))
        b = await service.create(_req(external_user_id="U2"))
        # Two people linking at the same time is the normal case, not a conflict.
        assert await service.peek(a) is not None
        assert await service.peek(b) is not None
        assert (await service.peek(a)).external_user_id == "U1"
        assert (await service.peek(b)).external_user_id == "U2"

    async def test_same_user_in_another_workspace_is_a_different_identity(self, svc):
        service, _ = svc
        a = await service.create(_req(external_team_id="T1"))
        b = await service.create(_req(external_team_id="T2"))
        assert await service.peek(a) is not None
        assert await service.peek(b) is not None


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateOrReuse:
    async def test_first_call_creates(self, svc):
        service, _ = svc
        token, reused = await service.create_or_reuse(_req())
        assert reused is False
        assert await service.peek(token) is not None

    async def test_second_call_reuses_the_same_token(self, svc):
        service, _ = svc
        first, _ = await service.create_or_reuse(_req())
        second, reused = await service.create_or_reuse(_req())
        # Re-sending the existing link, rather than minting a parallel one.
        assert second == first
        assert reused is True

    async def test_reuse_does_not_extend_the_ttl(self, svc):
        service, fake = svc
        token, _ = await service.create_or_reuse(_req())
        fake.ttls[f"link_nonce:{token}"] = 30  # as if 9.5 minutes had passed
        await service.create_or_reuse(_req(pending_turn={"text": "different"}))
        # Otherwise mentioning the agent every few minutes keeps one token alive
        # forever, and the bounded lifetime is the whole point.
        assert fake.ttls[f"link_nonce:{token}"] == 30

    async def test_reuse_refreshes_the_pending_turn(self, svc):
        service, _ = svc
        token, _ = await service.create_or_reuse(_req(pending_turn={"text": "first"}))
        await service.create_or_reuse(_req(pending_turn={"text": "second"}))
        # Linking should answer what they most recently asked.
        assert (await service.peek(token)).pending_turn == {"text": "second"}

    async def test_reuse_keeps_the_earlier_turn_without_keepttl(self):
        # Redis without KEEPTTL: rewriting the payload would drop the expiry, so the
        # older question stands. Worse UX than the newest one, but not wrong — and
        # far better than dropping the nonce and forcing a re-link.
        fake = _FakeRedis(supports_keepttl=False)
        service = LinkNonceService(redis_client=fake)
        token, _ = await service.create_or_reuse(_req(pending_turn={"text": "first"}))
        token2, reused = await service.create_or_reuse(
            _req(pending_turn={"text": "second"})
        )
        assert (token2, reused) == (token, True)
        assert (await service.peek(token)).pending_turn == {"text": "first"}
        assert fake.ttls[f"link_nonce:{token}"] == mod._TTL_S

    async def test_after_consuming_a_new_mention_creates_a_fresh_nonce(self, svc):
        service, _ = svc
        token, _ = await service.create_or_reuse(_req())
        await service.consume(token)
        again, reused = await service.create_or_reuse(_req())
        # A completed link must not be resurrected by a dangling pointer.
        assert again != token
        assert reused is False

    async def test_stale_pointer_to_a_missing_nonce_creates_fresh(self, svc):
        service, fake = svc
        fake.store["link_nonce_user:slack:T1:U1"] = "vanished-token"
        token, reused = await service.create_or_reuse(_req())
        assert reused is False
        assert token != "vanished-token"

    async def test_pointer_naming_a_different_identity_is_not_trusted(self, svc):
        service, fake = svc
        other = await service.create(_req(external_user_id="U2"))
        # Corrupt U1's pointer to name U2's live nonce. Reuse must refuse, or one
        # user could be handed a token that links someone else's identity.
        fake.store["link_nonce_user:slack:T1:U1"] = other
        token, reused = await service.create_or_reuse(_req(external_user_id="U1"))
        assert reused is False
        assert token != other
        assert (await service.peek(token)).external_user_id == "U1"


@pytest.mark.unit
@pytest.mark.asyncio
class TestClaimSend:
    async def test_allows_the_cap_then_refuses(self, svc):
        service, _ = svc
        req = _req()
        await service.create_or_reuse(req)
        allowed = [await service.claim_send(req) for _ in range(4)]
        # Two DMs about the same pending link, then the caller falls back to an
        # ephemeral in-channel notice rather than DMing again.
        assert allowed == [True, True, False, False]

    async def test_a_fresh_link_gets_a_fresh_budget(self, svc):
        service, _ = svc
        req = _req()
        await service.create_or_reuse(req)
        await service.claim_send(req)
        await service.claim_send(req)
        assert await service.claim_send(req) is False
        # A genuinely new link must never be silently withheld.
        await service.create(req)
        assert await service.claim_send(req) is True

    async def test_budget_is_per_identity(self, svc):
        service, _ = svc
        a, b = _req(external_user_id="U1"), _req(external_user_id="U2")
        await service.claim_send(a)
        await service.claim_send(a)
        assert await service.claim_send(a) is False
        assert await service.claim_send(b) is True

    async def test_counter_is_given_a_ttl(self, svc):
        service, fake = svc
        await service.claim_send(_req())
        assert fake.ttls["link_nonce_sends:slack:T1:U1"] == mod._TTL_S

    async def test_counter_without_an_expiry_is_repaired(self, svc):
        service, fake = svc
        # Simulates a crash between INCR and EXPIRE. Left alone, the key would never
        # expire and the user could never be DMed again.
        fake.store["link_nonce_sends:slack:T1:U1"] = "1"
        assert await service.claim_send(_req()) is True
        assert fake.ttls["link_nonce_sends:slack:T1:U1"] == mod._TTL_S


@pytest.mark.unit
@pytest.mark.asyncio
class TestRequiresRedis:
    async def test_missing_redis_raises_rather_than_degrading(self, monkeypatch):
        # Unlike the link cache (where a miss just means "read the DB"), there is no
        # safe fallback here — the alternative is trusting ids from the URL.
        import sys
        from types import SimpleNamespace

        fake_deps = SimpleNamespace(
            GlobalDependencies=lambda: SimpleNamespace(redis_pool=None)
        )
        monkeypatch.setitem(sys.modules, "src.config.dependencies", fake_deps)
        with pytest.raises(RuntimeError, match="requires Redis"):
            await LinkNonceService().create(_req())
