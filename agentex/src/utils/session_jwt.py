"""Reading the expiry out of an SGP session JWT.

The identity-link flow stores the linking user's own session cookie as the
credential it later acts through, so it needs to know when that cookie stops
working. The JWT carries that in its ``exp`` claim, which is more accurate than any
TTL we could invent: the credential's real lifetime belongs to the session, not to
us.

**This deliberately does not verify the signature.** It is not an authentication
check and must never be used as one. The token arrives on an already-authenticated
request — the auth middleware verified it, upstream, by asking the auth service —
and by the time we get here the only open question is "how long is this good for".
Verifying again would mean holding the signing key, which is precisely the thing
agentex should not have.

Because the claims are unverified, the expiry is treated as a hint: a *shorter*
expiry than reality only causes an early, recoverable re-link prompt, and a longer
one is caught anyway when the credential is rejected downstream.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime

from src.utils.logging import make_logger

logger = make_logger(__name__)


def _b64url_decode(segment: str) -> bytes:
    # JWT segments are base64url with the padding stripped; put it back or the
    # stdlib decoder rejects them.
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def claims(token: str) -> dict | None:
    """The JWT's payload claims, or None if it isn't a readable JWT.

    Unverified — see the module docstring.
    """
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        decoded = json.loads(_b64url_decode(parts[1]))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def expires_at(token: str) -> datetime | None:
    """When this session token stops being valid, or None if it doesn't say.

    None is a meaningful answer and must not be read as "never expires" — the
    caller is expected to substitute a bounded fallback, because storing a
    credential with no known expiry is how you end up holding one indefinitely.
    """
    payload = claims(token)
    if payload is None:
        return None
    exp = payload.get("exp")
    # bool is an int subclass, so it has to be excluded explicitly: exp=True would
    # otherwise become 1970-01-01, i.e. a credential that looks already-expired.
    if not isinstance(exp, int | float) or isinstance(exp, bool):
        return None
    try:
        return datetime.fromtimestamp(exp, UTC)
    except (OverflowError, OSError, ValueError):
        # A nonsense exp (far-future, negative) shouldn't crash a link attempt.
        logger.warning("[session_jwt] unusable exp claim; treating as unknown")
        return None
