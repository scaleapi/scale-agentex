"""Unit tests for reading a session token's expiry.

This decides how long a stored credential is trusted, so the cases that matter are
the malformed ones: anything unreadable must come back as "unknown" (None) so the
caller substitutes a bounded fallback. Returning a wrong-but-plausible datetime, or
raising, would be worse than admitting ignorance.

Note the deliberate absence of signature verification — see the module docstring in
src/utils/session_jwt.py. These tests use tokens with garbage signatures precisely
to pin that down.
"""

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
from src.utils import session_jwt


def _token(claims: dict, *, signature: str = "not-a-real-signature") -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJFUzI1NiJ9.{payload}.{signature}"


@pytest.mark.unit
class TestExpiresAt:
    def test_reads_the_exp_claim(self):
        when = datetime(2027, 1, 31, 22, 4, 41, tzinfo=UTC)
        got = session_jwt.expires_at(_token({"exp": int(when.timestamp())}))
        assert got == when

    def test_result_is_timezone_aware(self):
        got = session_jwt.expires_at(_token({"exp": 1801433081}))
        # A naive datetime compared against an aware "now" raises, which would turn
        # a link attempt into a 500.
        assert got is not None and got.tzinfo is not None

    def test_signature_is_not_verified(self):
        # Verifying would require holding the signing key, which is exactly what
        # agentex should not have. The claims are a hint, not an auth decision.
        exp = int((datetime.now(UTC) + timedelta(days=5)).timestamp())
        assert (
            session_jwt.expires_at(_token({"exp": exp}, signature="garbage"))
            is not None
        )

    def test_unpadded_base64_payload_is_handled(self):
        # JWTs strip base64 padding; the stdlib decoder rejects that unless it's
        # restored. A payload whose length isn't a multiple of 4 catches a
        # regression here.
        tok = _token({"exp": 1801433081, "pad": "x"})
        assert len(tok.split(".")[1]) % 4 != 0
        assert session_jwt.expires_at(tok) is not None


@pytest.mark.unit
class TestUnknownExpiry:
    @pytest.mark.parametrize(
        "token",
        [
            "",
            "not-a-jwt",
            "only.two",
            "a.b.c.d",
            "header.!!!not-base64!!!.sig",
        ],
    )
    def test_malformed_tokens_are_unknown_not_errors(self, token):
        assert session_jwt.expires_at(token) is None

    def test_payload_that_is_not_an_object(self):
        payload = base64.urlsafe_b64encode(b'"a string"').decode().rstrip("=")
        assert session_jwt.expires_at(f"h.{payload}.s") is None

    def test_missing_exp_is_unknown(self):
        assert session_jwt.expires_at(_token({"sub": "abc"})) is None

    @pytest.mark.parametrize("exp", ["soon", None, [], {}, True])
    def test_non_numeric_exp_is_unknown(self, exp):
        # `True` matters: bool is an int subclass, so a naive isinstance check would
        # accept it and produce 1970-01-01, i.e. a credential that looks expired.
        assert session_jwt.expires_at(_token({"exp": exp})) is None

    def test_absurd_exp_does_not_raise(self):
        assert session_jwt.expires_at(_token({"exp": 10**20})) is None


@pytest.mark.unit
class TestClaims:
    def test_returns_the_payload(self):
        got = session_jwt.claims(_token({"sub": "abc", "exp": 1}))
        assert got == {"sub": "abc", "exp": 1}

    def test_unreadable_token_is_none(self):
        assert session_jwt.claims("nope") is None
