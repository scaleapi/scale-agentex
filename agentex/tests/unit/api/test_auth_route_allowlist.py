"""The unauthenticated route allowlist is a security boundary, not a config list.

`is_whitelisted_route` decides which requests skip the auth provider entirely
(`AgentexAuthMiddleware.dispatch`). Anything it returns True for is served to
the internet with no principal, so each entry is asserted explicitly here
rather than inferred from the set.
"""

import pytest
from src.api.middleware_utils import WHITELISTED_ROUTES, is_whitelisted_route


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    [
        "/openapi.json",
        "/swagger",
        "/swagger/oauth2-redirect",
        "/api",
        "/api/",
        "/redoc",
        "/docs",
        "/docs/index.html",
    ],
)
def test_api_schema_and_docs_require_authentication(path):
    """The schema enumerates every route, parameter and model this service
    exposes; the docs describe its setup. Neither is served anonymously."""
    assert not is_whitelisted_route(path)


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    [
        "/health",
        "/healthz",
        "/readyz",
        "/ping",
        "/echo",
        "/favicon.ico",
        "/agents/register",
        "/agents/forward/name/some-agent/v1/messages",
    ],
)
def test_anonymous_routes_stay_anonymous(path):
    """Probes, the agent registration handshake and agent forwarding carry no
    user principal by design and must not start demanding one."""
    assert is_whitelisted_route(path)


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    [
        "/agents",
        "/agents/some-agent-id",
        "/agents/registered",
        "/tasks",
        "/messages",
        "/spans",
        "/health-metrics",
        "/echoes/1",
    ],
)
def test_resource_routes_are_authenticated(path):
    """Entries match a whole path segment, so a route that merely shares a
    prefix with an allowlisted one ("/agents/registered" vs
    "/agents/register") is not born anonymous."""
    assert not is_whitelisted_route(path)


@pytest.mark.unit
def test_allowlist_contents_are_pinned():
    """A new entry is a new piece of internet-facing anonymous surface. Adding
    one here is the prompt to say why in review."""
    assert WHITELISTED_ROUTES == {
        "/agents/register",
        "/agents/forward",
        "/slack",
        "/linear",
        "/favicon.ico",
        "/health",
        "/healthcheck",
        "/healthz",
        "/readyz",
        "/ping",
        "/echo",
    }
