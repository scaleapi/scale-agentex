"""Encrypt credentials that agentex has to hold at rest.

Used for the per-user SGP API keys the Slack/Linear gateways store so an
event-driven turn can act as the invoking human (see the identity-link entities).
Those keys open that user's connected integrations, so they are the most
sensitive thing this service persists.

The key lives in ``AGENTEX_CREDENTIAL_ENCRYPTION_KEY``, delivered the same way as
every other platform secret (the mounted secret JSON, exported into the
environment at startup). That placement is the entire point: the ciphertext sits
in Postgres and the key does not, so a database dump — a backup, a replica, a
stray ``pg_dump`` — is not sufficient to read the credentials.

Fernet rather than raw AES because it is *authenticated*: a tampered ciphertext
fails to decrypt instead of silently producing garbage that we'd then send to SGP
as a bearer token. It also carries a version byte and a timestamp, so the format
can be migrated later without guessing what a given blob is.

Fails closed. A missing or malformed key raises rather than falling back to
plaintext — storing an unencrypted credential because configuration was wrong is
exactly the outcome this module exists to prevent.
"""

from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

ENV_KEY = "AGENTEX_CREDENTIAL_ENCRYPTION_KEY"


class CredentialEncryptionError(RuntimeError):
    """Encryption is misconfigured, or a stored ciphertext could not be read."""


@lru_cache(maxsize=1)
def _cipher() -> Fernet:
    """The process-wide Fernet. Cached because constructing it parses the key.

    ``lru_cache`` also means a bad key is reported on first use rather than at
    import, so the service still starts (and can serve everything that doesn't
    touch stored credentials) with a clear error on the paths that do.
    """
    raw = os.getenv(ENV_KEY, "").strip()
    if not raw:
        raise CredentialEncryptionError(
            f"{ENV_KEY} is unset. Stored credentials cannot be read or written "
            f"without it; generate one with "
            f"`python -c 'from cryptography.fernet import Fernet; "
            f"print(Fernet.generate_key().decode())'` and deliver it with the "
            f"platform secrets."
        )
    try:
        return Fernet(raw.encode())
    except Exception as exc:  # noqa: BLE001 - any parse failure is the same class of bug
        raise CredentialEncryptionError(
            f"{ENV_KEY} is not a valid Fernet key (expected 32 url-safe "
            f"base64-encoded bytes)."
        ) from exc


def is_configured() -> bool:
    """Whether credential encryption is usable.

    Lets a caller degrade deliberately — e.g. a gateway that stores no
    credentials locally — instead of discovering the problem mid-turn.
    """
    try:
        _cipher()
        return True
    except CredentialEncryptionError:
        return False


def encrypt(plaintext: str) -> str:
    """Encrypt a credential for storage. Returns url-safe base64 text."""
    if not plaintext:
        raise CredentialEncryptionError("refusing to encrypt an empty credential")
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a stored credential.

    Raises on tampering or on a key that no longer matches the one used to write
    the row — both mean "this credential is unusable", which the caller must
    surface (prompt a re-link) rather than treat as an empty credential.
    """
    if not ciphertext:
        raise CredentialEncryptionError("refusing to decrypt an empty ciphertext")
    try:
        return _cipher().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise CredentialEncryptionError(
            "stored credential could not be decrypted — it was written with a "
            "different key, or the ciphertext was modified. The owner needs to "
            "re-link."
        ) from exc


def reset_cache() -> None:
    """Drop the cached cipher. For tests that change the key mid-process."""
    _cipher.cache_clear()
