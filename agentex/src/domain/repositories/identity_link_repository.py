"""Reads and writes identity links.

Two things to notice about the shape of this class:

1. Every read filters ``revoked_at IS NULL``, matching the partial unique
   indexes. A revoked row is history, never an answer. The lookups are
   deliberately narrow rather than a generic filter API so a caller can't
   accidentally resolve a tombstoned link.

2. The credential is reachable through exactly one method
   (``get_credential``), which returns a bare string and never an entity. All
   other reads go through ``IdentityLinkEntity``, which has no credential field.
   That asymmetry is intentional: entities get logged, cached and serialized, so
   the fewer paths that can put a key in one, the better.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select, update
from src.adapters.crud_store.adapter_postgres import PostgresCRUDRepository
from src.adapters.orm import IdentityLinkORM
from src.config.dependencies import (
    DDatabaseAsyncReadOnlySessionMaker,
    DDatabaseAsyncReadWriteSessionMaker,
)
from src.domain.entities.identity_links import (
    IdentityLinkEntity,
    IdentityLinkMethod,
    IdentityProvider,
)
from src.utils.credential_encryption import decrypt, encrypt
from src.utils.ids import orm_id
from src.utils.logging import make_logger

logger = make_logger(__name__)


def _to_entity(row: IdentityLinkORM) -> IdentityLinkEntity:
    """Map ORM -> entity, collapsing the ciphertext to a boolean.

    Done by hand rather than via ``model_validate`` so the credential physically
    cannot end up on the entity, even if someone later adds a matching field.
    """
    return IdentityLinkEntity(
        id=row.id,
        provider=row.provider,
        external_team_id=row.external_team_id,
        external_user_id=row.external_user_id,
        sgp_user_id=row.sgp_user_id,
        sgp_account_id=row.sgp_account_id,
        linked_via=row.linked_via,
        has_credential=bool(row.credential_ciphertext),
        credential_expires_at=row.credential_expires_at,
        linked_at=row.linked_at,
        revoked_at=row.revoked_at,
    )


class IdentityLinkRepository(
    PostgresCRUDRepository[IdentityLinkORM, IdentityLinkEntity]
):
    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
        async_read_only_session_maker: DDatabaseAsyncReadOnlySessionMaker,
    ):
        super().__init__(
            async_read_write_session_maker,
            async_read_only_session_maker,
            IdentityLinkORM,
            IdentityLinkEntity,
        )

    async def get_active_by_external_user(
        self,
        provider: IdentityProvider,
        external_team_id: str,
        external_user_id: str,
    ) -> IdentityLinkEntity | None:
        """The active link for a provider identity, or None if unlinked.

        The hot path — runs on every inbound event, behind a cache.
        """
        async with self.start_async_db_session(allow_writes=False) as session:
            row = (
                (
                    await session.execute(
                        select(IdentityLinkORM).where(
                            IdentityLinkORM.provider == provider,
                            IdentityLinkORM.external_team_id == external_team_id,
                            IdentityLinkORM.external_user_id == external_user_id,
                            IdentityLinkORM.revoked_at.is_(None),
                        )
                    )
                )
                .scalars()
                .first()
            )
            return _to_entity(row) if row else None

    async def get_active_by_sgp_user(
        self,
        provider: IdentityProvider,
        external_team_id: str,
        sgp_user_id: str,
    ) -> IdentityLinkEntity | None:
        """The active link pointing at an SGP user within one workspace.

        Used by the link path to detect a conflict *before* hitting
        ``uq_identity_links_sgp_user_active``, so the user sees "that SGP account
        is already linked to a different Slack user" rather than an integrity
        error.
        """
        async with self.start_async_db_session(allow_writes=False) as session:
            row = (
                (
                    await session.execute(
                        select(IdentityLinkORM).where(
                            IdentityLinkORM.provider == provider,
                            IdentityLinkORM.external_team_id == external_team_id,
                            IdentityLinkORM.sgp_user_id == sgp_user_id,
                            IdentityLinkORM.revoked_at.is_(None),
                        )
                    )
                )
                .scalars()
                .first()
            )
            return _to_entity(row) if row else None

    async def get_credential(self, link_id: str) -> str | None:
        """Decrypt and return this link's stored SGP credential.

        The ONLY path that produces a plaintext credential. Returns None when the
        link has none; raises ``CredentialEncryptionError`` when a ciphertext
        exists but can't be read (wrong key, tampering), because that must surface
        as "re-link needed" rather than as "no credential".
        """
        async with self.start_async_db_session(allow_writes=False) as session:
            ciphertext = await session.scalar(
                select(IdentityLinkORM.credential_ciphertext).where(
                    IdentityLinkORM.id == link_id,
                    IdentityLinkORM.revoked_at.is_(None),
                )
            )
        return decrypt(ciphertext) if ciphertext else None

    async def upsert_link(
        self,
        *,
        provider: IdentityProvider,
        external_team_id: str,
        external_user_id: str,
        sgp_user_id: str,
        sgp_account_id: str,
        linked_via: IdentityLinkMethod,
        credential: str | None = None,
        credential_expires_at: datetime | None = None,
    ) -> IdentityLinkEntity:
        """Create a link, revoking any existing active one for this identity.

        Revoke-then-insert rather than update-in-place, for two reasons: it keeps
        the previous mapping auditable, and it means re-linking is idempotent
        against the partial unique index instead of racing it.

        Both writes happen in one transaction, so there is never a window where an
        identity has two active links (which the index would reject anyway) or
        none (which would silently drop the user's access).
        """
        now = datetime.now(UTC)
        async with self.start_async_db_session(allow_writes=True) as session:
            async with session.begin():
                # Clear the superseded row's credential as well as tombstoning it.
                # Otherwise every re-link leaves behind a row holding a key that is
                # still valid until its own expiry, and a user who re-links a few
                # times accumulates a trail of working credentials at rest. The
                # tombstone's value is the mapping and its timestamps, not the key.
                await session.execute(
                    update(IdentityLinkORM)
                    .where(
                        IdentityLinkORM.provider == provider,
                        IdentityLinkORM.external_team_id == external_team_id,
                        IdentityLinkORM.external_user_id == external_user_id,
                        IdentityLinkORM.revoked_at.is_(None),
                    )
                    .values(
                        revoked_at=now,
                        credential_ciphertext=None,
                        credential_expires_at=None,
                    )
                )
                row = IdentityLinkORM(
                    id=orm_id(),
                    provider=provider,
                    external_team_id=external_team_id,
                    external_user_id=external_user_id,
                    sgp_user_id=sgp_user_id,
                    sgp_account_id=sgp_account_id,
                    linked_via=linked_via,
                    credential_ciphertext=encrypt(credential) if credential else None,
                    credential_expires_at=credential_expires_at,
                    linked_at=now,
                )
                session.add(row)
            logger.info(
                "identity_link_upserted",
                extra={
                    "provider": provider.value,
                    "external_team_id": external_team_id,
                    "external_user_id": external_user_id,
                    "sgp_user_id": sgp_user_id,
                    "linked_via": linked_via.value,
                    "has_credential": bool(credential),
                },
            )
            return _to_entity(row)

    async def revoke(
        self,
        provider: IdentityProvider,
        external_team_id: str,
        external_user_id: str,
    ) -> bool:
        """Tombstone the active link for a provider identity.

        Also clears the ciphertext: a revoked link should not leave a usable
        credential at rest, and the row's audit value is in the mapping and
        timestamps, not the key.
        """
        async with self.start_async_db_session(allow_writes=True) as session:
            async with session.begin():
                result = await session.execute(
                    update(IdentityLinkORM)
                    .where(
                        IdentityLinkORM.provider == provider,
                        IdentityLinkORM.external_team_id == external_team_id,
                        IdentityLinkORM.external_user_id == external_user_id,
                        IdentityLinkORM.revoked_at.is_(None),
                    )
                    .values(
                        revoked_at=datetime.now(UTC),
                        credential_ciphertext=None,
                        credential_expires_at=None,
                    )
                )
            return bool(result.rowcount)


DIdentityLinkRepository = Annotated[
    IdentityLinkRepository, Depends(IdentityLinkRepository)
]
