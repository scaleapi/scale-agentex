"""Integration tests for the link nonce against a real Redis.

The unit tests for this service run against a hand-written ``_FakeRedis``, so they
assert *our model* of Redis rather than Redis itself. Where that model is wrong, the
unit tests pass and production breaks. The cases here target exactly the places the
model could be wrong:

- ``decode_responses=False`` (what the app uses), so real Redis returns **bytes**
  where the fake returns ``str``. Every read path has to survive that.
- ``GETDEL`` really removing the key, and doing so atomically under concurrency.
- ``KEEPTTL`` really preserving an expiry while rewriting a value. The fake cannot
  prove this at all, and the whole "reuse must not extend the lifetime" guarantee
  rests on it.
- ``INCR`` / ``EXPIRE`` / ``TTL`` behaving as the send cap assumes, including the
  distinction between "exists, no expiry" (-1) and "missing" (-2).

Depends only on ``redis_url``, deliberately: the broader ``isolated_repositories``
fixture also starts Postgres and MongoDB, and none of this needs either. That keeps
the tests fast and lets them run in environments where the Mongo image won't boot.
The Redis container is session-scoped and shared, so each test namespaces its keys
by test name rather than flushing the database out from under its neighbours.
"""

import asyncio
import re

import pytest
import pytest_asyncio
from src.domain.services import link_nonce_service as mod
from src.domain.services.link_nonce_service import LinkNonceService, LinkRequest


@pytest_asyncio.fixture
async def redis(redis_url):
    """Client configured the way the application configures it — bytes, not str."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(redis_url, decode_responses=False)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def team(request):
    """Key namespace unique to this test; the Redis container is shared."""
    return "T_" + re.sub(r"\W+", "_", request.node.name)[:60]


@pytest.fixture
def service(redis):
    return LinkNonceService(redis_client=redis)


@pytest.fixture
def req(team):
    def _make(**kw) -> LinkRequest:
        return LinkRequest(
            **{
                "provider": "slack",
                "external_team_id": team,
                "external_user_id": "U1",
                "display_name": "@test.user",
                "pending_turn": {"text": "what's in my notion?"},
                **kw,
            }
        )

    return _make


@pytest.mark.integration
@pytest.mark.asyncio
class TestRealBytesHandling:
    async def test_payload_round_trips_through_real_redis(self, service, req):
        token = await service.create(req())
        got = await service.peek(token)
        assert got is not None
        assert got.external_user_id == "U1"
        assert got.pending_turn == {"text": "what's in my notion?"}

    async def test_reuse_finds_a_pointer_stored_as_bytes(
        self, service, req, redis, team
    ):
        # Real Redis returns the pointer as bytes. If that isn't decoded, reuse
        # silently misses and mints a parallel token — the very accumulation this
        # service exists to prevent. The fake hands back str, so it cannot catch it.
        first = await service.create(req())
        raw = await redis.get(f"link_nonce_user:slack:{team}:U1")
        assert isinstance(raw, bytes), "expected a client with decode_responses=False"

        second, reused = await service.create_or_reuse(req())
        assert (second, reused) == (first, True)

    async def test_stored_value_is_json(self, service, req, redis):
        token = await service.create(req())
        raw = await redis.get(f"link_nonce:{token}")
        # Guards against a refactor to str()/pickle, which a fake-backed round-trip
        # would still happily pass.
        assert raw.lstrip().startswith(b"{")


@pytest.mark.integration
@pytest.mark.asyncio
class TestSingleUseIsReal:
    async def test_consume_actually_removes_the_key(self, service, req, redis):
        token = await service.create(req())
        assert await service.consume(token) is not None
        assert await redis.get(f"link_nonce:{token}") is None
        assert await service.consume(token) is None

    async def test_concurrent_consume_yields_exactly_one_winner(self, service, req):
        # Two confirms racing on one token: a double-submit, or a retry. GETDEL is
        # what makes that safe; a read-then-delete would let both through and mint
        # two credentials for one link.
        token = await service.create(req())
        results = await asyncio.gather(*(service.consume(token) for _ in range(5)))
        assert sum(1 for r in results if r is not None) == 1

    async def test_superseded_token_is_really_deleted(self, service, req, redis):
        first = await service.create(req())
        second = await service.create(req())
        # Genuinely deleted, not merely unreachable: a live leftover is another
        # chance for a link to be redeemed by the wrong person, and consuming the
        # new one would not invalidate it.
        assert await redis.get(f"link_nonce:{first}") is None
        assert await redis.get(f"link_nonce:{second}") is not None


@pytest.mark.integration
@pytest.mark.asyncio
class TestExpiryIsReal:
    async def test_nonce_and_pointer_both_get_a_ttl(self, service, req, redis, team):
        token = await service.create(req())
        # -1 = exists with no expiry, -2 = missing. Either is a bug here: a nonce
        # that never expires is a permanent bearer token.
        for key in (f"link_nonce:{token}", f"link_nonce_user:slack:{team}:U1"):
            ttl = await redis.ttl(key)
            assert 0 < ttl <= mod._TTL_S, f"{key} ttl={ttl}"

    async def test_reuse_preserves_the_remaining_ttl(self, service, req, redis):
        """KEEPTTL, verified against Redis instead of against our own fake.

        The load-bearing case. Reuse rewrites the payload to carry the user's latest
        message; if that write dropped the expiry, someone mentioning the agent
        every few minutes would keep one token alive indefinitely and the bounded
        lifetime — the entire point of a nonce — would be gone.
        """
        token = await service.create(req(pending_turn={"text": "first"}))
        key = f"link_nonce:{token}"
        await redis.expire(key, 60)  # stand in for "most of the window has elapsed"

        again, reused = await service.create_or_reuse(
            req(pending_turn={"text": "second"})
        )
        assert (again, reused) == (token, True)

        ttl = await redis.ttl(key)
        assert 0 < ttl <= 60, f"reuse extended the lifetime: ttl={ttl}"
        # ...and the rewrite still landed.
        assert (await service.peek(token)).pending_turn == {"text": "second"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestSendCapAgainstRealRedis:
    async def test_cap_holds_and_counter_expires(self, service, req, redis, team):
        r = req()
        await service.create_or_reuse(r)
        allowed = [await service.claim_send(r) for _ in range(4)]
        assert allowed == [True, True, False, False]

        ttl = await redis.ttl(f"link_nonce_sends:slack:{team}:U1")
        assert 0 < ttl <= mod._TTL_S, f"send counter ttl={ttl}"

    async def test_concurrent_sends_do_not_exceed_the_cap(self, service, req):
        # INCR is atomic, so simultaneous mentions cannot both slip past the cap.
        r = req()
        await service.create_or_reuse(r)
        results = await asyncio.gather(*(service.claim_send(r) for _ in range(10)))
        assert sum(1 for x in results if x) == mod._MAX_SENDS

    async def test_a_fresh_nonce_resets_the_counter(self, service, req, redis, team):
        r = req()
        await service.create_or_reuse(r)
        await service.claim_send(r)
        await service.claim_send(r)
        assert await service.claim_send(r) is False

        await service.create(r)
        assert await redis.get(f"link_nonce_sends:slack:{team}:U1") is None
        # A genuinely new link must never be silently withheld.
        assert await service.claim_send(r) is True

    async def test_counter_left_without_an_expiry_is_repaired(
        self, service, req, redis, team
    ):
        # Simulates a crash between INCR and EXPIRE. Real Redis reports -1 for such
        # a key; left alone it would outlive every nonce and the user could never be
        # DMed again.
        key = f"link_nonce_sends:slack:{team}:U1"
        await redis.set(key, "1")
        assert await redis.ttl(key) == -1

        assert await service.claim_send(req()) is True
        assert await redis.ttl(key) > 0


@pytest.mark.integration
@pytest.mark.asyncio
class TestIdentityIsolation:
    async def test_two_users_linking_at_once_do_not_collide(self, service, req):
        a = await service.create(req(external_user_id="U1"))
        b = await service.create(req(external_user_id="U2"))
        assert a != b
        assert (await service.peek(a)).external_user_id == "U1"
        assert (await service.peek(b)).external_user_id == "U2"

    async def test_send_budgets_are_independent(self, service, req):
        a, b = req(external_user_id="U1"), req(external_user_id="U2")
        await service.claim_send(a)
        await service.claim_send(a)
        assert await service.claim_send(a) is False
        assert await service.claim_send(b) is True
