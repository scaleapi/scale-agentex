# API and platform worker observability adapters

The API can use an optional Python module for deployment-specific logs, traces,
and metrics. Set `AGENTEX_OBSERVABILITY_MODULE` to its import path before
starting Uvicorn. If the variable is unset or the selected module is not
installed, the API keeps its built-in telemetry.

An installed, selected adapter replaces built-in instrumentation. The API skips
its automatic instrumentation, native metric provider, StatsD,
and PostgreSQL/Redis collectors. Application loggers keep their sensitive-text
filter and propagate to the adapter's handlers. Database operations and product
span storage continue normally.

Custom application metrics use an adapter's optional `get_meter` callback. If
the callback is absent, adapter mode stops `auth_cache.access`,
`auth_cache.eviction`, and `agent_run_schedule.temporal_op`; generic HTTP,
database, and Redis metrics do not replace them. Before enabling an adapter
without this callback, identify dashboards and alerts using these series and
preserve or replace any required signals. Native PostgreSQL and Redis collectors
remain disabled either way.

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
instrumentation should require a plain process launch and document how to turn
off competing automatic instrumentation.

## Platform Temporal worker

The `src.temporal.run_worker` entry point supports the same module selector for
the platform `agentex-server` task queue. This does not configure customer agent
or SDK workers. Use a worker adapter module that implements `initialize_worker()`
and `shutdown()`, and set the selector before importing the entry point:

```sh
AGENTEX_OBSERVABILITY_MODULE=example_telemetry.worker \
  python -m src.temporal.run_worker
```

`initialize_worker()` runs once before dependency and client imports, so the
adapter can instrument library constructors before they are used. Select the
API and worker modules separately for each process. Missing selected modules
keep native telemetry; installed modules with broken callbacks fail startup.
Unset the selector and restart the worker to return to native telemetry.

Two optional synchronous callbacks extend the adapter contract:

```python
def temporal_client_interceptors():
    return []


def get_meter(name: str, version: str):
    return None
```

The client factory applies `temporal_client_interceptors()` once to each client,
including the dependency client and the polling client. Temporal automatically
uses client interceptors that also implement its worker interceptor interface.
Do not register those interceptors again on `Worker`. `get_meter` must return a
meter from the adapter's provider, or `None`; it must not create a provider for
each call.

Temporal Core metrics keep their separate exporter and default interval. The
worker prefers `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` over
`OTEL_EXPORTER_OTLP_ENDPOINT`; HTTP appends `/v1/metrics` only to the base endpoint.
Protocol precedence is `OTEL_EXPORTER_OTLP_METRICS_PROTOCOL`, then
`OTEL_EXPORTER_OTLP_PROTOCOL`, then `http/protobuf`. Set `grpc` for gRPC receivers.
Without an OTel endpoint, `DD_AGENT_HOST` remains the gRPC fallback on port 4317
(or its explicit port). Python metric providers do not replace Core's Rust
metrics; do not add another Core exporter or runtime through the adapter.

On SIGTERM, the worker stops polling, gives activities a ten-second grace
period, then closes HTTP clients and dependencies before flushing the adapter
in a thread. Adapters should configure bounded exporter timeouts. The process
manager's termination grace period remains the limit for unresponsive cleanup.

Before enabling the adapter, set an explicit pod termination grace period and
configure any service mesh to keep outbound connections available through the
ten-second activity drain, dependency cleanup, and final telemetry flush. Allow
additional time before the pod deadline. Verify these settings in the rendered
deployment and test SIGTERM during active work and autoscaling scale-in with the
actual proxy and a slow collector. An idle local shutdown test does not verify
those deployment conditions.

Workflow logs use Temporal's replay-aware logger in adapter mode. Credential
redaction runs on the Temporal workflow and activity loggers, so it survives
adapter handler replacement. Non-JSON health responses log only status and size
in both modes. Other healthcheck failures omit untrusted values in adapter mode.

## Request IDs and logs

The request middleware accepts an inbound `x-request-id` with 1–128 printable
ASCII characters and no spaces. It generates a UUID for missing or invalid
headers, stores the ID in `request.state.request_id` and `ctx_var_request_id`,
forwards it through cached HTTP clients, and echoes it on responses. Explicit
outbound headers take precedence. Context lasts through streams and resets when
the request finishes or fails. The outer health interceptor still bypasses
application middleware for probes.

Inbound IDs are accepted for correlation; validation prevents unsafe log text,
not spoofing. Deployments that need service-controlled IDs must have a trusted
ingress overwrite caller-supplied `x-request-id`; directly exposed deployments
otherwise retain caller-controlled IDs.

An adapter can bind its own logging context in outer middleware. Accept or
generate the ID there, put it in the request headers, and keep the context active
through the response. The public middleware reuses that ID.

A structured-field allowlist cannot remove values embedded in message text.
General log-call cleanup is separate from adapter setup.

## Verification

Run from `agentex/`:

```sh
uv run python -m pytest tests/unit/utils/test_observability.py tests/unit/api/test_observability_lifespan.py tests/unit/config/test_observability_dependencies.py tests/unit/api/test_request_logging_middleware.py tests/unit/utils/test_http_request_id.py
uv run python -m pytest tests/integration/test_observability_adapter.py
uv run python -m pytest tests/unit/temporal/test_worker_observability.py tests/unit/temporal/test_run_worker_metrics_url.py tests/unit/temporal/test_healthcheck_activities.py
```

The integration test uses two real Uvicorn workers and HTTP requests. It replaces
remote dependency startup with test callbacks; it does not verify a deployment
or delivery to a telemetry backend.
