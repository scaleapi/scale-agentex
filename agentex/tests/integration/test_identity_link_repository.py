"""Integration tests for IdentityLinkRepository against a real Postgres.

These need a real database, not mocks, because the behaviors that matter are
enforced by the schema and by SQL rather than by Python:

- the two *partial* unique indexes (scoped to ``revoked_at IS NULL``), which are how
  "one active link per identity" is enforced while keeping revoked rows for audit
- the revoke-then-insert transaction in ``upsert_link``
- round-tripping a Fernet ciphertext through a text column

The single most important case here is
``test_superseding_a_link_clears_the_old_credential``. That was a real bug: the
first implementation tombstoned the previous row but left its ciphertext intact, so
every re-link accumulated another row holding a still-valid SGP key. A mock-based
test would have passed happily.
"""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import text
from src.domain.entities.identity_links import IdentityLinkMethod, IdentityProvider
from src.domain.repositories.identity_link_repository import IdentityLinkRepository
from src.utils import credential_encryption as ce

_SECRET = "ssk_is_" + "a" * 32
_OTHER_SECRET = "ssk_is_" + "b" * 32
_TEAM = "T_ITEST"


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    """A real Fernet key for the duration of each test."""
    ce.reset_cache()
    monkeypatch.setenv(ce.ENV_KEY, Fernet.generate_key().decode())
    yield
    ce.reset_cache()


@pytest_asyncio.fixture
async def repo(isolated_repositories):
    return IdentityLinkRepository(
        isolated_repositories["postgres_rw_session_factory"],
        isolated_repositories["postgres_ro_session_factory"],
    )


async def _link(repo, *, user="U1", sgp_user="sgp-1", credential=_SECRET, expires=None):
    return await repo.upsert_link(
        provider=IdentityProvider.SLACK,
        external_team_id=_TEAM,
        external_user_id=user,
        sgp_user_id=sgp_user,
        sgp_account_id="acct-1",
        linked_via=IdentityLinkMethod.EXPLICIT,
        credential=credential,
        credential_expires_at=expires,
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestRoundTrip:
    async def test_entity_never_exposes_the_credential(self, repo):
        link = await _link(repo)
        dumped = link.model_dump()
        assert "credential" not in dumped
        assert "credential_ciphertext" not in dumped
        assert _SECRET not in str(dumped)
        # Callers still need to know whether the agent *can* act as this user.
        assert link.has_credential is True

    async def test_credential_round_trips_through_the_database(self, repo):
        link = await _link(repo)
        assert await repo.get_credential(link.id) == _SECRET

    async def test_stored_column_is_ciphertext_not_plaintext(
        self, repo, isolated_repositories
    ):
        link = await _link(repo)
        engine = isolated_repositories["postgres_engine"]
        async with engine.connect() as conn:
            raw = await conn.scalar(
                text("SELECT credential_ciphertext FROM identity_links WHERE id = :i"),
                {"i": link.id},
            )
        assert raw and _SECRET not in raw
        assert raw.startswith("gAAAA")  # Fernet token prefix

    async def test_link_without_a_credential_is_valid(self, repo):
        link = await _link(repo, credential=None)
        assert link.has_credential is False
        assert await repo.get_credential(link.id) is None

    async def test_expiry_is_persisted_and_drives_usability(self, repo):
        past = datetime.now(UTC) - timedelta(minutes=1)
        link = await _link(repo, expires=past)
        assert link.credential_expires_at is not None
        assert link.credential_is_usable(now=datetime.now(UTC)) is False


@pytest.mark.integration
@pytest.mark.asyncio
class TestResolution:
    async def test_resolves_by_provider_identity(self, repo):
        await _link(repo, user="U1")
        got = await repo.get_active_by_external_user(
            IdentityProvider.SLACK, _TEAM, "U1"
        )
        assert got is not None and got.sgp_user_id == "sgp-1"

    async def test_team_is_part_of_the_identity(self, repo):
        await _link(repo, user="U1")
        assert (
            await repo.get_active_by_external_user(
                IdentityProvider.SLACK, "T_OTHER", "U1"
            )
            is None
        )

    async def test_provider_is_part_of_the_identity(self, repo):
        await _link(repo, user="U1")
        assert (
            await repo.get_active_by_external_user(IdentityProvider.LINEAR, _TEAM, "U1")
            is None
        )

    async def test_resolves_by_sgp_user_for_conflict_detection(self, repo):
        await _link(repo, user="U1", sgp_user="sgp-1")
        got = await repo.get_active_by_sgp_user(IdentityProvider.SLACK, _TEAM, "sgp-1")
        assert got is not None and got.external_user_id == "U1"


@pytest.mark.integration
@pytest.mark.asyncio
class TestSupersedeAndRevoke:
    async def test_relinking_supersedes_rather_than_colliding(
        self, repo, isolated_repositories
    ):
        first = await _link(repo, user="U1", credential=_SECRET)
        second = await _link(repo, user="U1", credential=_OTHER_SECRET)

        assert second.id != first.id
        engine = isolated_repositories["postgres_engine"]
        async with engine.connect() as conn:
            active = await conn.scalar(
                text(
                    "SELECT count(*) FROM identity_links "
                    "WHERE external_user_id = 'U1' AND revoked_at IS NULL"
                )
            )
        # The partial unique index permits exactly one active row per identity.
        assert active == 1
        assert await repo.get_credential(second.id) == _OTHER_SECRET

    async def test_superseding_a_link_clears_the_old_credential(
        self, repo, isolated_repositories
    ):
        # REGRESSION: superseding used to tombstone the row but leave its ciphertext,
        # so each re-link left behind another still-valid SGP key at rest.
        await _link(repo, user="U1", credential=_SECRET)
        await _link(repo, user="U1", credential=_OTHER_SECRET)

        engine = isolated_repositories["postgres_engine"]
        async with engine.connect() as conn:
            leftover = await conn.scalar(
                text(
                    "SELECT count(*) FROM identity_links "
                    "WHERE external_user_id = 'U1' AND revoked_at IS NOT NULL "
                    "AND credential_ciphertext IS NOT NULL"
                )
            )
        assert leftover == 0

    async def test_revoke_tombstones_and_clears_the_credential(
        self, repo, isolated_repositories
    ):
        await _link(repo, user="U1")
        assert await repo.revoke(IdentityProvider.SLACK, _TEAM, "U1") is True

        assert (
            await repo.get_active_by_external_user(IdentityProvider.SLACK, _TEAM, "U1")
            is None
        )
        engine = isolated_repositories["postgres_engine"]
        async with engine.connect() as conn:
            rows, with_key = (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM identity_links WHERE external_user_id='U1'"
                    )
                ),
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM identity_links WHERE external_user_id='U1'"
                        " AND credential_ciphertext IS NOT NULL"
                    )
                ),
            )
        # Row kept for audit, credential gone.
        assert rows == 1
        assert with_key == 0

    async def test_revoking_an_unlinked_identity_is_a_no_op(self, repo):
        assert await repo.revoke(IdentityProvider.SLACK, _TEAM, "U-nope") is False

    async def test_relink_after_revoke_succeeds(self, repo):
        await _link(repo, user="U1")
        await repo.revoke(IdentityProvider.SLACK, _TEAM, "U1")
        again = await _link(repo, user="U1", credential=_OTHER_SECRET)
        assert await repo.get_credential(again.id) == _OTHER_SECRET

    async def test_two_slack_users_cannot_share_one_sgp_user(self, repo):
        # Defense in depth: two provider identities pointing at one SGP user is the
        # shape an identity hijack takes.
        await _link(repo, user="U1", sgp_user="sgp-shared")
        with pytest.raises(Exception):  # noqa: B017 - driver-specific integrity error
            await _link(repo, user="U2", sgp_user="sgp-shared")


@pytest.mark.integration
@pytest.mark.asyncio
class TestCredentialFailureModes:
    async def test_unreadable_ciphertext_raises_rather_than_returning_none(
        self, repo, isolated_repositories
    ):
        # A rotated encryption key must surface as "re-link needed", never as
        # "this user has no credential" — the latter silently downgrades the turn.
        link = await _link(repo)
        engine = isolated_repositories["postgres_engine"]
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE identity_links SET credential_ciphertext = 'gAAAAAtampered'"
                    " WHERE id = :i"
                ),
                {"i": link.id},
            )
        with pytest.raises(ce.CredentialEncryptionError):
            await repo.get_credential(link.id)

    async def test_credential_of_a_revoked_link_is_not_returned(self, repo):
        link = await _link(repo)
        await repo.revoke(IdentityProvider.SLACK, _TEAM, "U1")
        assert await repo.get_credential(link.id) is None
