# API observability adapter

The API can use an optional Python module for deployment-specific logs, traces,
and metrics. Set `AGENTEX_OBSERVABILITY_MODULE` to its import path before
starting Uvicorn. If the variable is unset or the selected module is not
installed, the API keeps its built-in telemetry.

An installed, selected adapter replaces built-in instrumentation. The API skips
its automatic instrumentation, native metric provider, custom metrics, StatsD,
and PostgreSQL/Redis collectors. Application loggers keep their sensitive-text
filter and propagate to the adapter's handlers. Database operations and product
span storage continue normally.

The adapter is installed separately. The public backend does not depend on its
package or a particular telemetry backend.

Images that bundle instrumentation for an adapter can set
`AGENTEX_OTEL_REQUIRE_SDK_SETUP=true`. Native startup then requires an installed
OpenTelemetry distribution or configurator before auto-instrumenting libraries.
Injected SDK setup still runs in each worker; built-in custom metrics are
unaffected. The default is `false`, preserving public backend behavior.

## Callback contract

Implement two synchronous functions. Importing the adapter must not install
handlers, providers, or instrumentation.

```python
def initialize(app) -> None:
    # Configure logging, traces, and metrics for the completed FastAPI app.
    pass


def shutdown() -> None:
    # Flush and close resources created by the adapter.
    pass
```

`initialize(app)` runs once per app after routes, mounts, and middleware are
registered, before Uvicorn builds the middleware stack or loads application
dependencies. Configure logging here. Adapter mode adds no application output
handlers or exception hook before initialization.

`shutdown()` runs once per process in a thread after application cleanup. It
also runs when initialization or dependency startup fails. It must tolerate
partial initialization and close only resources the adapter owns. The
`AsyncExitStack` still runs remaining cleanup if another cleanup step raises.

An installed adapter with a missing dependency, or an initialization error,
fails startup. Only absence of the selected module falls back to built-in
telemetry. Selection is cached for the life of the process; restart after
changing it. Every Uvicorn worker initializes independently.

The API hook does not initialize background workers. Adapters that own all
instrumentation should require a plain server launch and document how to turn
off competing automatic instrumentation.

## Request IDs and logs

The request middleware accepts an inbound `x-request-id` with 1–128 printable
ASCII characters and no spaces. It generates a UUID for missing or invalid
headers, stores the ID in `request.state.request_id` and `ctx_var_request_id`,
forwards it through cached HTTP clients, and echoes it on responses. Explicit
outbound headers take precedence. Context lasts through streams and resets when
the request finishes or fails. The outer health interceptor still bypasses
application middleware for probes.

An adapter can bind its own logging context in outer middleware. Accept or
generate the ID there, put it in the request headers, and keep the context active
through the response. The public middleware reuses that ID.

Application log messages are unchanged. A structured-field allowlist cannot
remove values embedded in message text. Log-call cleanup is separate.

## Verification

Run from `agentex/`:

```sh
uv run python -m pytest tests/unit/utils/test_observability.py tests/unit/api/test_observability_lifespan.py tests/unit/config/test_observability_dependencies.py tests/unit/api/test_request_logging_middleware.py tests/unit/utils/test_http_request_id.py
uv run python -m pytest tests/integration/test_observability_adapter.py
```

The integration test uses two real Uvicorn workers and HTTP requests. It replaces
remote dependency startup with test callbacks; it does not verify a deployment
or delivery to a telemetry backend.
