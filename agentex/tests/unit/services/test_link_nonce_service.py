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
    """Enough Redis for the nonce: get/set/getdel/delete with TTL capture."""

    def __init__(self, *, supports_getdel=True):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.supports_getdel = supports_getdel

    async def set(self, key, value, ex=None):
        self.store[key] = value
        self.ttls[key] = ex

    async def get(self, key):
        return self.store.get(key)

    async def getdel(self, key):
        if not self.supports_getdel:
            raise AttributeError("GETDEL unsupported")
        return self.store.pop(key, None)

    async def delete(self, key):
        self.store.pop(key, None)


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
