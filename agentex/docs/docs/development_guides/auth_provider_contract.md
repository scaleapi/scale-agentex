# Auth Provider Contract (`AGENTEX_AUTH_URL`)

Agentex delegates **authentication** (who is calling?) and **authorization** (are
they allowed to do this?) to an external HTTP service. You point Agentex at that
service with a single environment variable:

```bash
AGENTEX_AUTH_URL=https://my-auth-provider.internal
```

This document specifies the HTTP contract that service must satisfy. Anyone can
implement it from this spec alone. This makes the auth provider a **documented
extension point**: a naive single-account implementation is a few dozen lines,
while a full multi-tenant implementation can layer in fine-grained access control
behind the same wire format.

> **Scope.** This contract covers the endpoints a self-hosted / open-source
> deployment needs: `/v1/authn` plus the authorization endpoints `grant`,
> `revoke`, `check`, `search`, `register`, and `deregister`. Fine-grained access
> control (FGAC), per-account routing, and dual-write rollouts are out of scope
> and are **not** part of this contract.

---

## How Agentex calls the provider

- **Disabled by default.** If `AGENTEX_AUTH_URL` is unset or empty, the auth
  middleware is disabled: all authentication is skipped and all authorization
  checks are bypassed (every request is treated as fully authorized). This is the
  default local-development behavior — you only run an auth provider when you set
  the variable.
- **Authentication is middleware.** On every non-allowlisted request, Agentex
  forwards the incoming request headers to `POST {AGENTEX_AUTH_URL}/v1/authn`. A
  `200` returns a **principal context** that Agentex attaches to the request; any
  failure becomes a `401` to the original caller.
- **Authorization is inline.** When handling a request, Agentex calls the
  `/v1/authz/*` endpoints, passing back the exact principal context it received
  from `/v1/authn`.
- **Responses are cached.** Agentex caches successful `/v1/authn` results keyed on
  the forwarded headers. Provider responses should therefore be a pure function of
  the request headers.

### Allowlisted (unauthenticated) routes

These routes bypass the provider entirely and are never sent to `/v1/authn`:

```
/agents/register   /agents/forward   /docs   /api   /openapi.json   /redoc
/favicon.ico   /health   /healthcheck   /healthz   /readyz   /ping   /echo
```

(plus any sub-path under them, and all `OPTIONS` preflight requests).

---

## Conventions

| Aspect | Value |
| --- | --- |
| Transport | HTTP/1.1, JSON request and response bodies (`Content-Type: application/json`) |
| Method | All endpoints are `POST` |
| Base path | `AGENTEX_AUTH_URL` is the origin; paths below are appended verbatim |
| Auth of the provider itself | Out of scope — secure the network path (mTLS / private network / shared secret) as you see fit |

### Status code semantics

The Agentex client interprets the HTTP **status code**, not the response body, to
decide what happened. The body matters only where noted (`/v1/authn` principal,
`search` items).

| Status | Meaning to Agentex | Resulting behavior |
| --- | --- | --- |
| `200` | Success | Proceed. For `check`, the principal is authorized. For `search`, read `items`. |
| `401` | Unauthenticated — missing/invalid credentials | Request rejected as `401 Unauthorized` |
| `403` | Authenticated but not permitted | Treated as a permission denial (e.g. `check` failed) |
| `502` | Provider acted as a bad gateway | Surfaced as a gateway error |
| `503` | Provider temporarily unavailable | Surfaced as service-unavailable |
| other `5xx` | Provider internal error | Surfaced as a service error |
| other non-`200` | Unexpected | Surfaced as a service error |

A network/timeout failure reaching the provider is treated as service-unavailable.

> **`/v1/authn` collapses every failure to `401`.** The status-code distinctions
> above (`502`/`503`/`5xx`) are preserved only for the **authz** endpoints, which
> are called inside request handlers. Authentication runs in middleware that
> catches *any* non-`200` from the provider — including `5xx` — and returns a flat
> `401 Unauthorized` to the original caller. A `503` from your authn endpoint
> during an outage will therefore reach clients as `401`, not as a retryable
> service-unavailable error.

### The principal context (opaque round-trip)

The **principal context** is a JSON object returned by `/v1/authn`. Agentex treats
it as **opaque** — it does not inspect or validate its shape. It caches the object,
attaches it to the request, and passes it back **verbatim** as the `principal`
field of every subsequent authorization call.

The practical consequence: **the provider owns its own identity shape end to
end.** You can return whatever JSON your authz logic needs (a user id, an account
id, claims from a JWT, etc.) and it will be handed straight back to you on
`grant` / `revoke` / `check` / `search` / `register` / `deregister`. Agentex is
just a courier.

Example (one possible shape — yours can differ):

```json
{
  "user_id": "user_123",
  "account_id": "acct_456",
  "service_account_id": null,
  "metadata": {}
}
```

### Shared request types

Authorization requests share a small vocabulary.

**Resource** — the object being acted on:

```json
{ "type": "agent", "selector": "agent_abc123" }
```

| Field | Type | Notes |
| --- | --- | --- |
| `type` | enum string | One of `agent`, `task`, `api_key`, `schedule` |
| `selector` | string | The resource id |

**Operation** — one of: `create`, `read`, `update`, `delete`, `execute`, `cancel`.

---

## Authentication

### `POST /v1/authn`

Verify the caller's credentials and return their principal context.

**Request.** Agentex forwards the incoming request's headers (lowercased) as the
outbound request headers. It strips hop-by-hop headers (`content-length`, `host`,
`connection`, `transfer-encoding`, `expect`). The request body is empty — **all
input is in the headers.** The provider reads whatever credential headers it
cares about, for example:

- `authorization: Bearer <token>` (e.g. an OIDC / Entra ID access token)
- `x-api-key: <key>`
- `cookie: <session>`

**Response — `200`:** the principal context (any JSON object). This becomes the
`principal` for all later authz calls.

```json
{ "user_id": "user_123", "account_id": "acct_456", "metadata": {} }
```

**Response — `401`:** credentials missing or invalid. Agentex rejects the original
request with `401 Unauthorized`.

---

## Authorization

All authorization endpoints receive the principal context (exactly as returned by
`/v1/authn`) under the `principal` key.

> **Agent-to-agent calls.** Requests bearing a valid internal agent API key
> (`x-agent-api-key`) are authenticated by Agentex directly against its own
> database and **do not** hit the provider. The provider only sees end-user /
> service-account traffic.

### `POST /v1/authz/check`

The core read gate. Determine whether the principal may perform `operation` on
`resource`.

**Request:**

```json
{
  "principal": { "user_id": "user_123", "account_id": "acct_456" },
  "resource": { "type": "task", "selector": "task_789" },
  "operation": "read"
}
```

**Response:**

- `200` → **allowed**. Body: `{ "success": true }` (body is not otherwise read).
- `403` → **denied**.

### `POST /v1/authz/search`

List the resource ids of a given type that the principal may access. Agentex uses
the returned `items` to **scope list endpoints** — effectively a
`WHERE id IN (items)` filter over the resources of that type.

**Request:**

```json
{
  "principal": { "user_id": "user_123", "account_id": "acct_456" },
  "filter_resource": "task",
  "filter_operation": "read"
}
```

**Response — `200`:**

```json
{ "items": ["task_1", "task_2", "task_3"], "success": true }
```

| Field | Type | Notes |
| --- | --- | --- |
| `items` | `string[]` | Resource ids the principal may access. **Required.** |

> ⚠️ **`items` is an inclusion filter, not a hint.** Returning `[]` hides *every*
> resource of that type from the principal. There is no "all resources" sentinel
> in the base contract, so a provider that intends to grant broad access must
> return the actual set of accessible ids.

### `POST /v1/authz/grant`

Grant `operation` on `resource` to the principal (explicit sharing).

**Request:** same shape as `check`. **Response:** `200` with `{ "success": true }`.

### `POST /v1/authz/revoke`

Revoke a previously granted `(principal, resource, operation)` edge.

**Request:** same shape as `check`. **Response:** `200` with `{ "success": true }`.

### `POST /v1/authz/register`

Called by Agentex when a resource is **created** (agents, tasks, api keys,
schedules). Registers the new resource with the principal as its owner, optionally
linking it to a parent resource so that permission checks can cascade.

**Request:**

```json
{
  "principal": { "user_id": "user_123", "account_id": "acct_456" },
  "resource": { "type": "task", "selector": "task_789" },
  "parent": { "type": "agent", "selector": "agent_abc123" }
}
```

`parent` may be `null`. **Response:** `200` with `{ "success": true }`.

### `POST /v1/authz/deregister`

Called by Agentex when a resource is **deleted**. Removes the resource and all of
its relationships.

**Request:**

```json
{
  "principal": { "user_id": "user_123", "account_id": "acct_456" },
  "resource": { "type": "task", "selector": "task_789" }
}
```

**Response:** `200` with `{ "success": true }`.

> **`register`/`deregister` are not optional to *implement*, even though their
> behavior can be trivial.** Agentex calls them on every create/delete whenever a
> provider is configured. A provider that omits them (returning `404`) will turn
> every resource create into a `500`. A permissive provider should return `200`
> from both (see below).

### Endpoint summary

| Endpoint | Purpose | Success | Denial |
| --- | --- | --- | --- |
| `POST /v1/authn` | Authenticate, return principal | `200` + principal | `401` |
| `POST /v1/authz/check` | Read gate | `200` | `403` |
| `POST /v1/authz/search` | List accessible ids | `200` + `{items}` | `200` + `{items: []}` |
| `POST /v1/authz/grant` | Share a resource | `200` | `403` |
| `POST /v1/authz/revoke` | Un-share a resource | `200` | `403` |
| `POST /v1/authz/register` | Register created resource | `200` | `403` |
| `POST /v1/authz/deregister` | Remove deleted resource | `200` | `403` |
