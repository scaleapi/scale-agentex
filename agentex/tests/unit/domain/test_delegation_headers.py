"""Unit tests for runtime delegation header construction."""

from src.domain.delegation_headers import (
    HEADER_ACTING_USER_API_KEY,
    HEADER_ACTING_USER_COOKIE,
    build_delegation_headers,
)


def _user_principal():
    return type("Principal", (), {"user_id": "user-1", "account_id": "acct-1"})()


class TestBuildDelegationHeaders:
    def test_api_key_delegation(self):
        headers = build_delegation_headers(
            _user_principal(),
            {
                "x-api-key": "user-key",
                "x-selected-account-id": "acct-1",
            },
        )
        assert headers == {
            HEADER_ACTING_USER_API_KEY: "user-key",
            "x-selected-account-id": "acct-1",
        }

    def test_cookie_delegation_when_no_api_key(self):
        cookie = "_identityJwt=eyJhbGciOiJIUzI1NiJ9.test; other=value"
        headers = build_delegation_headers(
            _user_principal(),
            {"Cookie": cookie, "x-selected-account-id": "acct-2"},
        )
        assert headers == {
            HEADER_ACTING_USER_COOKIE: cookie,
            "x-selected-account-id": "acct-2",
        }

    def test_prefers_api_key_when_both_present(self):
        headers = build_delegation_headers(
            _user_principal(),
            {
                "x-api-key": "user-key",
                "cookie": "_identityJwt=jwt",
            },
        )
        assert HEADER_ACTING_USER_API_KEY in headers
        assert HEADER_ACTING_USER_COOKIE not in headers

    def test_skips_when_no_principal(self):
        assert build_delegation_headers(None, {"x-api-key": "k"}) == {}

    def test_skips_when_agent_identity(self):
        assert (
            build_delegation_headers(
                _user_principal(),
                {"x-api-key": "k"},
                agent_identity="agent-1",
            )
            == {}
        )

    def test_empty_when_no_credential(self):
        assert build_delegation_headers(_user_principal(), {"x-trace-id": "t"}) == {}
