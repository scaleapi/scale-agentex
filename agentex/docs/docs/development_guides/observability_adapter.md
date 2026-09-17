# API observability adapter

The API can use an optional Python module for deployment-specific logs, traces,
and metrics. Set `AGENTEX_OBSERVABILITY_MODULE` to its import path before
starting Uvicorn. When the variable is unset, the API uses its built-in logging and
OpenTelemetry setup and imports no adapter.

The adapter is installed separately. The public backend does not require its
package or any particular logging backend.

## Callback contract

Implement these synchronous functions:

```python
def initialize_logging() -> bool:
    # Install application logging handlers and formatting here.
    return True


def configure_app(app) -> None:
    # Configure tracing and metrics on the completed FastAPI app here.
    pass


def shutdown() -> None:
    # Flush and close only resources created by this adapter.
    pass
```

1. `initialize_logging()` runs once per process, before application modules
   create loggers and before the normal OpenTelemetry bootstrap. Return `True`
   only after installing logging handlers. Agentex loggers then propagate to
   those handlers, keep their sensitive-text filter, and add no output handler
   or exception hook. Return `False` to retain built-in logging. Avoid importing
   application modules from this callback.
2. `configure_app(app)` runs once for each app, after all application routes,
   mounts and middleware are registered. It runs before the outer health-check
   wrapper and before Uvicorn builds the middleware stack. The existing
   OpenTelemetry bootstrap and native metric provider initialization have already
   run. Reuse installed providers and exporters. HTTP instrumentation should
   have one owner. An adapter may add metric collectors alongside native
   collectors during adoption; overlapping measurements must be expected.
3. `shutdown()` runs once in a thread during API lifespan cleanup. It also runs
   when lifespan startup or another cleanup step fails. It must tolerate partial
   initialization. Close resources the adapter created, and leave adopted
   providers running. Callbacks should undo incomplete changes before raising.

Callback failures produce a diagnostic and let the API continue. A failed
logging callback keeps built-in logging and skips app configuration; shutdown
still runs for the imported adapter. With `CI=true`, failures raise instead, so
tests cannot silently pass with a disabled adapter.

Each Uvicorn worker loads the module separately. The normal bootstrap adds the
worker PID to `service.instance.id`, including when automatic instrumentation
packages are absent. Keep provider and initialization state local to the process.
The API does not configure other entry points, such as background workers.

The native application metrics, database collectors and product spans keep
their existing setup and shutdown. An adapter should preserve those paths.
The normal bootstrap skips OpenTelemetry HTTP instrumentors when Datadog owns
the matching HTTP libraries. It preserves the configured instrumentor exclusions
and still initializes the SDK, other instrumentors and custom metrics.

## Request IDs and log fields

The request middleware accepts an inbound `x-request-id` with 1–128 printable
ASCII characters and no spaces. It generates a UUID when that header is missing
or invalid. It stores the value in `request.state.request_id` and the existing
`ctx_var_request_id`, forwards it through cached HTTP clients, and echoes it on
responses. An explicit outbound header takes precedence. Context lasts through
streaming and resets when the request finishes or fails. Health probes handled
by the outer interceptor keep bypassing application middleware.

Existing application log messages are unchanged. A structured-field allowlist
cannot remove values already embedded in message text. Log-call cleanup is
separate from the adapter interface.

To bind another logging context, an adapter may install middleware outside the
request middleware. Accept or generate the ID there, write the chosen header
into the request scope, and keep its context active through the response. The
public middleware will reuse that value. Always reset context after completion.

Run the focused checks from `agentex/`:

```sh
uv run python -m pytest tests/unit/utils/test_observability.py tests/unit/api/test_observability_lifespan.py tests/unit/api/test_request_logging_middleware.py tests/unit/utils/test_http_request_id.py
uv run python -m pytest tests/integration/test_observability_adapter.py
```

The integration test starts two local Uvicorn workers and uses real HTTP. It
replaces database startup with test callbacks; it does not verify database
connectivity, deployment configuration or telemetry delivery to a backend.
