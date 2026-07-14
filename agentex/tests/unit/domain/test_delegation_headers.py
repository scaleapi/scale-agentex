"""Unit tests for runtime delegation header construction."""

import pytest
from src.domain.delegation_headers import (
    ENV_SESSION_COOKIE_NAMES,
    HEADER_ACTING_USER_API_KEY,
    HEADER_ACTING_USER_AUTHORIZATION,
    HEADER_ACTING_USER_COOKIE,
    build_delegation_headers,
    session_cookie_names_to_forward,
)


def _user_principal():
    return type("Principal", (), {"user_id": "user-1", "account_id": "acct-1"})()


class TestSessionCookieNames:
    def test_default_when_env_unset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv(ENV_SESSION_COOKIE_NAMES, raising=False)
        assert session_cookie_names_to_forward() == ("_identityJwt",)

    def test_empty_env_disables(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv(ENV_SESSION_COOKIE_NAMES, "")
        assert session_cookie_names_to_forward() == ()

    def test_override_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv(ENV_SESSION_COOKIE_NAMES, "session, other")
        assert session_cookie_names_to_forward() == ("session", "other")


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

    def test_cookie_delegation_forwards_only_configured_names(self):
        cookie = "_identityJwt=eyJ.test; csrf=secret"
        headers = build_delegation_headers(
            _user_principal(),
            {"Cookie": cookie, "x-selected-account-id": "acct-2"},
        )
        assert headers == {
            HEADER_ACTING_USER_COOKIE: "_identityJwt=eyJ.test",
            "x-selected-account-id": "acct-2",
        }

    def test_cookie_delegation_survives_messy_browser_header(self):
        """Real browsers send long Cookie headers full of morsels that
        http.cookies.SimpleCookie cannot parse (analytics cookies with spaces and
        parentheses, '#' chars, base64 '=='). The parser must still extract the
        allowlisted _identityJwt sitting among them — otherwise cookie delegation
        silently drops to {} and agent pods get no acting credential (regression:
        SimpleCookie.load() aborted on the first bad morsel and lost the rest)."""
        cookie = (
            "_fbp=fb.1.1757359049951.112906694371483372; "
            "__utmzz=utmcsr=google|utmcmd=organic|utmccn=(not set)|utmctr=(not provided); "
            "fs_uid=#25WP4#678b3617:a3955fc3::1#96c136b6##/1809111214; "
            "_identityJwt=eyJhbGciOiJFUzI1NiJ9.payload.sig; "
            "__q_state_bbwZsKT3=eyJ1dWlkIjoiZDc1NDhjMDQ9PQ==; "
            "OptanonConsent=isGpcEnabled=0&groups=C0001%3A1%2CC0002%3A1&geolocation=US%3BOR; "
            "_jwt=eyJhbGciOiJFUzI1NiJ9.payload2.sig2"
        )
        headers = build_delegation_headers(
            _user_principal(),
            {"Cookie": cookie, "x-selected-account-id": "acct-9"},
        )
        assert headers == {
            HEADER_ACTING_USER_COOKIE: "_identityJwt=eyJhbGciOiJFUzI1NiJ9.payload.sig",
            "x-selected-account-id": "acct-9",
        }

    def test_cookie_delegation_respects_custom_names(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv(ENV_SESSION_COOKIE_NAMES, "session")
        headers = build_delegation_headers(
            _user_principal(),
            {"cookie": "session=abc; _identityJwt=ignored"},
        )
        assert headers == {HEADER_ACTING_USER_COOKIE: "session=abc"}

    def test_cookie_delegation_off_when_env_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv(ENV_SESSION_COOKIE_NAMES, "")
        assert (
            build_delegation_headers(
                _user_principal(),
                {"cookie": "_identityJwt=jwt"},
            )
            == {}
        )

    def test_cookie_delegation_skips_when_no_matching_cookie(self):
        assert (
            build_delegation_headers(
                _user_principal(),
                {"cookie": "csrf=secret"},
            )
            == {}
        )

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

    def test_bearer_delegation(self):
        headers = build_delegation_headers(
            _user_principal(),
            {
                "Authorization": "Bearer eyJ.oneauth.token",
                "x-selected-account-id": "acct-3",
            },
        )
        assert headers == {
            HEADER_ACTING_USER_AUTHORIZATION: "Bearer eyJ.oneauth.token",
            "x-selected-account-id": "acct-3",
        }

    def test_bearer_delegation_is_lowest_precedence(self):
        """A bearer alongside an api key or cookie never wins — those flows are
        unchanged, so only callers with a bearer and neither of the other two
        (OneAuth) reach the new branch."""
        api_key_wins = build_delegation_headers(
            _user_principal(),
            {"x-api-key": "user-key", "Authorization": "Bearer tok"},
        )
        assert api_key_wins == {HEADER_ACTING_USER_API_KEY: "user-key"}

        cookie_wins = build_delegation_headers(
            _user_principal(),
            {"cookie": "_identityJwt=jwt", "Authorization": "Bearer tok"},
        )
        assert cookie_wins == {HEADER_ACTING_USER_COOKIE: "_identityJwt=jwt"}

    def test_bearer_used_when_cookie_has_no_session_morsel(self):
        """A browser OIDC caller sends analytics/CSRF cookies alongside the
        bearer. The non-allowlisted Cookie header must not pre-empt the bearer."""
        headers = build_delegation_headers(
            _user_principal(),
            {"cookie": "csrf=secret", "Authorization": "Bearer tok"},
        )
        assert headers == {HEADER_ACTING_USER_AUTHORIZATION: "Bearer tok"}

    def test_non_bearer_authorization_ignored(self):
        assert (
            build_delegation_headers(
                _user_principal(),
                {"Authorization": "Basic dXNlcjpwYXNz"},
            )
            == {}
        )

    def test_bearer_scheme_is_case_insensitive(self):
        headers = build_delegation_headers(
            _user_principal(),
            {"authorization": "bearer lower.case.scheme"},
        )
        assert headers == {HEADER_ACTING_USER_AUTHORIZATION: "bearer lower.case.scheme"}

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
