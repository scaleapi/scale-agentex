"""
Regression test for the OPTIONS/CORS preflight 500 caused by FastAPI's
``_IncludedRouter`` change.

FastAPI 0.137.0 made ``app.routes`` a tree that can contain ``_IncludedRouter``
wrapper objects (one per ``include_router()`` call). Those wrappers do NOT
expose a ``.path`` attribute. The OpenTelemetry FastAPI auto-instrumentation
(injected at runtime by the observability operator, so it is not a dependency we
can bump here) reads ``route.path`` on a ``Match.PARTIAL`` while building the
request span. A browser CORS preflight (``OPTIONS``) has no declared endpoint,
so it only PARTIAL-matches the ``_IncludedRouter`` -> ``AttributeError`` raised
inside the ASGI layer (outside FastAPI's exception handlers) -> HTTP 500.

The only lever we control is the FastAPI version we ship, so we pin
``fastapi < 0.137.0`` to keep ``app.routes`` a flat list of routes that all
expose ``.path``. Pinning *up* does not help: 0.137.1/0.137.2/0.138.0 keep the
``_IncludedRouter`` and only add a new ``iter_route_contexts()`` helper that the
pinned injected instrumentation does not use.

If this test fails, FastAPI has been bumped to a version that reintroduces the
preflight-crash regression for the injected OTel instrumentation.
"""

import pytest
from src.api.app import fastapi_app
from starlette.routing import Match


@pytest.mark.unit
class TestOtelRouteCompat:
    def test_every_route_exposes_path(self):
        """Every entry in app.routes must expose ``.path`` (what OTel reads)."""
        missing = [
            type(route).__name__
            for route in fastapi_app.routes
            if not hasattr(route, "path")
        ]
        assert not missing, (
            "Routes without a `.path` attribute would crash the injected OTel "
            f"FastAPI instrumentation on OPTIONS preflights: {missing}. "
            "This usually means FastAPI was bumped to >= 0.137.0."
        )

    def test_options_preflight_route_matching_does_not_crash(self):
        """Simulate OTel `_get_route_details` over an OPTIONS preflight scope."""
        scope = {
            "type": "http",
            "method": "OPTIONS",
            "path": "/agents",
            "headers": [],
        }
        for route in fastapi_app.routes:
            match, _ = route.matches(scope)
            if match in (Match.FULL, Match.PARTIAL):
                assert route.path is not None
