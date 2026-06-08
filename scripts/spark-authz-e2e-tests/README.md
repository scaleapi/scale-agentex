# Spark AuthZ E2E tests

End-to-end tests for FGAC on `scale-agentex` routes. Black-box: every test
hits the real `scale-agentex` HTTP API as one identity, then verifies the
resulting state in SpiceDB via a separate Spark-AuthZ client.

Modeled after the equivalent KB suite in
`scaleapi/packages/egp-api-backend/scripts/spark-authz-e2e-tests/` (PR
[#142983](https://github.com/scaleapi/scaleapi/pull/142983)).

## Scope

AGX1-325 `agent_api_keys` routes: create / get / get-by-name / list /
delete / delete-by-name.

- **create** dual-writes to SpiceDB with the `parent_agent` edge populated.
- **get** / **get-by-name** are gated by `api_key.read`; denial collapses to 404.
- **list** filters to the api_keys the caller has `read` on.
- **delete** / **delete-by-name** dual-write deregisters; denial collapses to 404.

AGX1-327 `states` routes:

- **list/get** delegate read authorization to the parent task.
- **list** filters to states whose parent tasks the caller can view.
- **get** collapses denied parent-task view to 404.

## Setup

The suite does not spin up any services itself — it assumes the relevant
backends are already running (same model as the EGP suite this is mirrored
from). Three terminals + the test runner.

### Terminal 1 — `spark-authz` (authz server + Identity Service + SpiceDB)

```bash
cd ~/spark-authz
docker compose up
```

This brings up everything the authz layer needs in one shot: Postgres,
SpiceDB, Redis, schema migration, dev seed data, the `authz` server on
gRPC `50052` + HTTP `8090`, and `identity-service` on the port its compose
file binds. The suite talks to `localhost:8090` (HTTP-transcoded) for all
direct authz assertions.

### Terminal 2 — `agentex-auth` (the principal-resolution proxy)

```bash
cd ~/agentex/agentex-auth
# Start command depends on the repo's own dev-loop — see its README.
# Must be configured with IDENTITY_SERVICE_URL pointing at the one from
# Terminal 1, and SPARK_AUTHZ_URL pointing at localhost:8090.
```

`scale-agentex` forwards every request's headers to this service to resolve
the principal context (`user_id`, `service_account_id`, `account_id`).
Without it, `scale-agentex` 401s every request.

### Terminal 3 — `scale-agentex` itself

```bash
cd ~/scale-agentex/agentex
# uv run uvicorn ... — see agentex/Makefile for the exact dev target.
# Must be started with AGENTEX_AUTH_URL pointing at the agentex-auth from
# Terminal 2 (otherwise auth is bypassed and the assertions in this suite
# become meaningless).
```

### Terminal 4 — run the suite

```bash
cd ~/scale-agentex/scripts/spark-authz-e2e-tests
make install                       # one-time: venv + deps
cp config.json.example config.json # one-time
# Edit config.json — fill in real headers + identity_ids + account_id
# (see "Auth model" below for what those need to be).
make test                          # all tests
# See `make help` for the full list of targets, including logical groups
# (test-direct-resources) and per-resource targets.
```

### Minting credentials

The two `users` in `config.json` need to exist in Identity Service AND be
known to `agentex-auth`. The suite does **not** create them — they're
minted out-of-band, same as the EGP suite's `ssk_is_…` keys. Two paths:

- **Dev cluster**: grab existing dev API keys / bearer tokens for two real
  users in the same account and paste them in. Easiest if you have them.
- **Local stack**: use the seed identities that `spark-authz`'s
  `authz-dev-seed` container creates, or mint fresh ones via the local
  Identity Service after Terminal 1 comes up.

`user_b` must **not** be pre-granted access to `user_a`'s resources — the
negative-path tests depend on user_b having no role on user_a's agent /
api_key by default.

## Run

Targets are grouped so you can run a single test file, all tests for one
resource, all tests in a logical category, or the whole suite.

```bash
# Everything
make test

# Logical groups
make test-direct-resources    # resources with their own SpiceDB type (api_key, …)
make test-sub-resources       # resources that delegate to a parent

# One resource (all cases)
make test-api-key             # AGX1-325 — all api_key cases
make test-state               # AGX1-327 — all state cases

# One case
make test-api-key-create
make test-api-key-get
make test-api-key-list
make test-api-key-delete
make test-state-list-get
```

Adding a new resource? Add a `<RESOURCE>_TESTS` variable in the Makefile,
append it to `DIRECT_RESOURCE_TESTS` or `SUB_RESOURCE_TESTS`, and add a
`test-<resource>` target. See the existing entries for the shape.

## When spark-authz isn't reachable

Some environments (e.g. `sgp-pubsec-dev`) run scale-agentex without the
spark-authz HTTP frontend — there's raw SpiceDB but no `:8090` REST surface
for direct permission assertions. The suite degrades gracefully:

- Tests that **only hit scale-agentex HTTP routes** (most of the suite) run
  normally and assert on response codes + bodies.
- Tests that **assert directly against SpiceDB** (currently:
  `test_api_key_create.py`, `test_owner_delete_deregisters_in_spicedb`,
  and `test_state_list_get.py`)
  skip with a clear reason when `spark_authz.host` doesn't answer `/healthz`.
- The factory cleanup falls back to REST-only when spark-authz isn't
  reachable (no SpiceDB delete-resource call). Tuples may leak in this
  mode, but routes are the unit under test.

To run the SpiceDB-asserting tests, either point `spark_authz.host` at a
reachable spark-authz instance or set up a port-forward to one.

## Layout

```
clients/
  agentex_client.py        # httpx wrapper for /agents, /tasks, /states, /agent_api_keys
  spark_authz_client.py    # httpx wrapper for spark-authz REST
helpers/
  cleanup.py               # LIFO cleanup tracker honoring config knobs
  factories.py             # unique names for agents, api_keys, tasks
tests/
  test_api_key_create.py   # dual-write + parent_agent edge
  test_api_key_get.py      # 200 owner / 404 non-owner on id + name
  test_api_key_list.py     # FGAC list filter
  test_api_key_delete.py   # deregister on delete + non-owner 404
  test_state_list_get.py   # parent-task view delegation
conftest.py                # config, identities, clients, factories, cleanup
config.json.example        # template — copy to config.json and fill in
```

## Auth model

`scale-agentex`'s middleware forwards request headers to `agentex-auth`,
which resolves them to a principal context (user_id, service_account_id,
account_id). The test client doesn't care what flavor of header the target
environment requires — drop whatever `agentex-auth` accepts into
`users.<key>.headers` in `config.json` and the client passes it through.

## Cleanup model

Every factory registers a teardown that **first** tries `DELETE` via the REST
route (exercises the dual-write deregister) and **then** issues
`SparkAuthzClient.delete_resource` as a fallback. The second call is
idempotent — `NOT_FOUND` is swallowed server-side — so it's safe to always
run, and it prevents owner-tuple leaks if the REST dual-write deregister
silently fails between tests.
