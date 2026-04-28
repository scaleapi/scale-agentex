# Authz List Pagination — Design

**Status:** Draft
**Date:** 2026-04-28
**Owner:** Stas Moreinis

## Problem

When `agentex` lists authorized resources (today: tasks, with the same pattern reused for several other resource types), it relies on the FastAPI dependency `DAuthorizedResourceIds` (`agentex/src/utils/authorization_shortcuts.py:130-143`) to fetch the full set of resource IDs the principal is authorized for, then passes that set as a SQL `IN (...)` filter to the DB list query.

That dependency calls `AuthorizationService.list_resources` → `AgentexAuthorizationProxy.list_resources` (`POST /v1/authz/search`) → `agentex-auth` → `SGPAuthorization.list_resources`, which calls SGP `GET /private/v5/agentex/permissions?resources=task:*&limit=999&sort_order=desc` (`agentex-auth/src/adapters/authorization/adapter_sgp_authorization.py:120-153`).

SGP caps the result set at 999 regardless of any pagination input. Because the IN-list is *bounded* before paging happens, a principal with more than 999 authorized resources can never see more than 999 of them — paging at the agentex layer just walks within that frozen 999.

This is a correctness ceiling that grows naturally as accounts age. Tasks are the immediate concern, but every consumer of `DAuthorizedResourceIds` is at risk over time.

## Goals

- Remove the 999-resource ceiling on `agentex` list endpoints, starting with `GET /tasks`.
- Generalize the fix so all consumers of `DAuthorizedResourceIds` can adopt it with mechanical changes.
- Read-side fix only: do not introduce a write-side dependency (no permission mirroring in agentex's DB).
- Backwards compatible at the route level: existing callers using `limit` + `page_number` keep working without changes; cursor pagination is added as a new opt-in mode.

## Non-goals

- Changing the SGP API or its 999-row limit. Treat it as a fixed external constraint.
- Denormalizing `account_id` (or other principal fields) onto resources to bypass the permission table — explicitly off the table per project preference.
- Sub-999-row performance optimization. Existing list endpoints with small N stay roughly as fast as today.
- Removing `DAuthorizedResourceIds` immediately. It stays until all consumers migrate; cleanup happens in the final rollout phase.

## Architectural choice

**Filter-then-authorize**, read-side only. Instead of pre-fetching every authorized ID and passing it as a DB filter, we:

1. Page the DB with normal filters (cursor or offset).
2. For each DB page, batch-check authorization against `agentex-auth` using the *specific* candidate IDs.
3. Drop unauthorized rows.

The 999 cap on SGP is on output rows of a `resources=type:*` query. Querying `resources=type:id1,type:id2,...` returns at most one row per input selector, so for any input ≤ 999 the answer is complete. The SGP adapter chunks larger inputs internally and unions results.

`agentex-auth` and the agentex backend stay stateless with respect to each other; no new tables, no migrations, no dual-write concerns.

## Components

### 1. `agentex-auth` — new batch primitive

**Gateway port** — `AuthorizationGateway` gains:

```python
async def check_batch(
    self,
    principal: TPrincipal,
    resource_type: AgentexResourceType,
    selectors: list[str],
    operation: AuthorizedOperationType,
) -> set[str]:
    """Return the subset of selectors the principal is authorized for."""
```

**SGP adapter** (`adapter_sgp_authorization.py`) implements `check_batch` by issuing `GET /private/v5/agentex/permissions` with explicit `resources=[type:id1, type:id2, ...]` selectors. Inputs > 999 are split into 999-sized chunks; the adapter unions the chunked results and returns the full authorized set.

**HTTP endpoint** — `POST /v1/authz/check_batch`:

```python
class CheckBatchRequest(BaseModel):
    principal: PrincipalContext
    resource_type: AgentexResourceType
    selectors: list[str]
    operation: AuthorizedOperationType = AuthorizedOperationType.read

class CheckBatchResponse(BaseModel):
    authorized_selectors: list[str]
```

Existing `/v1/authz/grant`, `/v1/authz/revoke`, `/v1/authz/check`, `/v1/authz/search` are untouched. `/search` remains in service for any not-yet-migrated `DAuthorizedResourceIds` consumer; it is removed in the final rollout phase.

### 2. `agentex` backend — service + dependency

**Proxy adapter** — `AgentexAuthorizationProxy.check_batch` POSTs to `/v1/authz/check_batch` and returns the response set. Empty `selectors` short-circuits without an HTTP call.

**`AuthorizationService.check_batch`** — cache-aware split of inputs:

- For each selector, consult `auth_cache.get_authorization_check`.
- Selectors with cached `True` go into the result set.
- Selectors with cached `False` are dropped.
- Selectors with cache miss are sent to the gateway in one call.
- Gateway results are written back to the cache (both allowed and denied) before returning.

In bypass mode (agent identity present, or authz disabled), returns `set(selectors)` without any cache or gateway interaction.

**Public `is_bypassed()` method** on `AuthorizationService`. Promoted from the existing private `_bypass()`. Required so the new dependency can short-circuit cleanly. The method is stable API; `_bypass()` becomes a thin alias for backward compatibility within the class and is removed once internal callers migrate.

**`AuthorizationFilter` + `DAuthorizationFilter`** in `agentex/src/utils/authorization_shortcuts.py`:

```python
class AuthorizationFilter:
    def __init__(self, authz, resource_type, operation):
        self._authz = authz
        self._resource_type = resource_type
        self._operation = operation

    async def filter(self, candidate_ids: list[str]) -> set[str]:
        return await self._authz.check_batch(
            self._resource_type, candidate_ids, self._operation,
        )

    @property
    def is_bypassed(self) -> bool:
        return self._authz.is_bypassed()


def DAuthorizationFilter(
    resource_type: AgentexResourceType,
    operation: AuthorizedOperationType = AuthorizedOperationType.read,
):
    async def _build(authz: DAuthorizationService) -> AuthorizationFilter:
        return AuthorizationFilter(authz, resource_type, operation)
    return Annotated[AuthorizationFilter, Depends(_build)]
```

`DAuthorizedResourceIds` stays. Endpoints migrate one at a time.

### 3. `agentex` backend — pagination

**Cursor format** — opaque, base64-encoded JSON:

```json
{
  "v": 1,
  "ob": "created_at",
  "od": "desc",
  "sv": "2026-04-21T18:30:00Z",
  "id": "task_abc123"
}
```

Fields:

- `v` — cursor schema version. Mismatched versions return 400.
- `ob` — `order_by` column name. Validated against the request: if the request's `order_by` differs, return 400 ("cursor was issued for a different sort").
- `od` — `order_direction` (`asc` | `desc`). Same validation as `ob`.
- `sv` — last sort value, string-encoded. Decoded according to the column's type. NULL is encoded as a sentinel (`null` JSON literal).
- `id` — last row id, used as a deterministic tiebreaker for keyset comparisons.

**Sortable columns are allowlisted per ORM/entity** (e.g. `TaskEntity.SORTABLE_COLUMNS = {"created_at", "updated_at", "name", "status"}`). Any `order_by` outside the allowlist returns 400. This protects against SQL injection through `order_by` and rules out sorting on columns without indexes.

**Repository keyset query** — a generalized `list_keyset` method on `PostgresCRUDRepository` (or the per-entity repository, depending on whether existing patterns prefer generic or specific):

```python
async def list_keyset(
    self,
    *,
    sort_column: str,
    sort_direction: Literal["asc", "desc"],
    after: tuple[Any, str] | None,
    limit: int,
    filters: dict | None = None,
    relationships: list | None = None,
    extra_query_modifiers: Callable | None = None,
) -> list[Entity]:
    ...
```

Builds `WHERE (sort_col, id) < (sv, last_id)` for desc (`> (sv, last_id)` for asc) using row-value comparison so the tiebreaker is correct. NULL handling uses `(col IS NULL AND id < last_id) OR (col < last_sv)` form.

`extra_query_modifiers` is the escape hatch for join-based filters (e.g. `agent_id` → `JOIN task_agents`); each migrating route passes its own modifier rather than the generic method needing to know about every route's filters.

**Cursor mode use case** — single round-trip, ragged pages allowed:

```python
async def list_tasks_cursor(
    self,
    *,
    authz_filter: AuthorizationFilter,
    cursor: TasksCursor | None,
    limit: int,
    order_by: str,
    order_direction: str,
    ...other filters
) -> tuple[list[TaskEntity], TasksCursor | None]:
    page = await self.task_repo.list_keyset(
        sort_column=order_by,
        sort_direction=order_direction,
        after=(cursor.sort_value, cursor.id) if cursor else None,
        limit=limit,
        ...
    )
    if not page:
        return [], None

    last_db_row = page[-1] if len(page) == limit else None  # capture BEFORE filter

    if not authz_filter.is_bypassed:
        authorized = await authz_filter.filter([t.id for t in page])
        page = [t for t in page if t.id in authorized]

    next_cursor = None
    if last_db_row is not None:
        next_cursor = TasksCursor(
            order_by=order_by,
            order_direction=order_direction,
            sort_value=getattr(last_db_row, order_by),
            id=last_db_row.id,
        )
    return page, next_cursor
```

Capturing `last_db_row` *before* filtering is the non-obvious correctness bit: a page with 100% denied rows still emits a valid `next_cursor` pointing past the denied region, so callers don't infer "end of results" prematurely.

**Legacy mode use case** — walk-until-filled, full pages preserved:

```python
async def list_tasks_legacy(
    self,
    *,
    authz_filter: AuthorizationFilter,
    page_number: int,
    limit: int,
    ...
) -> list[TaskEntity]:
    target_skip = (page_number - 1) * limit
    accumulated: list[TaskEntity] = []
    db_offset = 0
    chunk_size = max(limit, 100)
    skipped_authorized = 0

    while len(accumulated) < limit:
        page = await self.task_repo.list_with_offset(
            offset=db_offset, limit=chunk_size, ...,
        )
        if not page:
            break

        if authz_filter.is_bypassed:
            authorized_subset = page
        else:
            authorized = await authz_filter.filter([t.id for t in page])
            authorized_subset = [t for t in page if t.id in authorized]

        for row in authorized_subset:
            if skipped_authorized < target_skip:
                skipped_authorized += 1
                continue
            accumulated.append(row)
            if len(accumulated) >= limit:
                break

        db_offset += len(page)

    return accumulated
```

Deep `page_number` is O(`page_number` × `chunk_size`) DB queries — acceptable as a back-compat shim, not a long-term answer. Logged with a structured warning above a threshold (5 DB roundtrips for a single request).

### 4. `agentex` backend — route changes

`agentex/src/api/routes/tasks.py` — `GET /tasks`:

- Adds query params: `cursor: str | None = None`.
- Existing `page_number: int | None = None` (was `int = 1` — default flips to `None` so we can detect "caller used cursor" vs "caller used legacy").
- `limit` is clamped to 999 at the route layer (validation error if exceeded).
- If both `cursor` and `page_number` are present → 400.
- If `cursor` present → cursor mode use case; emit `next_cursor` as `X-Next-Cursor` HTTP header.
- Else → legacy mode use case; the `X-Next-Cursor` header is not set.
- When the cursor mode reaches the end of results (`next_cursor` is `None`), the `X-Next-Cursor` header is also not set. Cursor-aware clients treat "header absent" as the unambiguous end-of-results signal.
- Response body remains `list[TaskResponse]` — no shape change.

The `X-Next-Cursor` header keeps the response body identical to today, so legacy callers (UI, SDK consumers) see no change. Cursor-aware clients read the header to keep paging.

## Edge cases

- **`limit > 999`** → 400 from the route validator.
- **Empty candidate list** → `AuthorizationFilter.filter([])` short-circuits to `set()`, no HTTP call.
- **All-denied page in cursor mode** → returns `(items=[], next_cursor=<cursor past denied region>)`. Caller continues walking.
- **Bypass** (agent identity / authz disabled) → `AuthorizationFilter.is_bypassed` short-circuits, no `check_batch` call, no cache traffic, query runs unmodified.
- **Stale cursor** (request `order_by` doesn't match cursor's `ob`) → 400.
- **Mismatched cursor schema version** → 400 ("cursor expired, please re-paginate").
- **NULL sort values** → cursor encodes `null`; SQL clause uses `(col IS NULL AND id < last_id) OR (col < last_sv)` form. Consistent with `NULLS LAST` for desc / `NULLS FIRST` for asc.
- **Cache eviction mid-list** → not a correctness concern. Each page is independently authorized; stale cache TTLs are bounded by the existing cache configuration for `check`.
- **Concurrent batch checks for overlapping IDs** → both may miss and both call SGP. Idempotent; cache gets written twice. No lock needed.

## Testing

**Unit tests:**

- `agentex-auth/tests/unit/test_sgp_authorization.py` — `check_batch` chunks correctly at 999, unions results, handles empty input, all-denied, mixed.
- `agentex/tests/unit/test_authorization_service.py` — cache-aware split: all-hit skips gateway; all-miss calls gateway with full set; mixed calls gateway with misses only; gateway results cached for both allowed and denied selectors; bypass short-circuits without cache traffic.
- `agentex/tests/unit/test_tasks_use_case.py` — cursor mode: empty page → `(_, None)`; full DB chunk fully filtered → `next_cursor` points past denied region; partial DB chunk (< limit) → `next_cursor=None`.
- `agentex/tests/unit/test_tasks_use_case.py` — legacy mode: walk-until-filled fills exactly `limit` rows when authorized rows are sparse; `target_skip` correctly skips prior pages' worth of authorized rows; returns short page when DB is exhausted.
- Cursor encoding: round-trip encode → decode; version mismatch → 400; `order_by` mismatch → 400; null sort-value handling.

**Integration tests** (`tests/integration/`):

- Seed > 1500 tasks for one principal; cursor walk visits all of them (not capped at 999).
- Seed 100 tasks where principal owns 30 (interleaved); legacy `page_number=1&limit=10` returns 10 *authorized* rows (not 10 DB rows of which some are denied).
- Cross-principal: principal A creates tasks; principal B lists; B sees only B's authorized subset across both modes.
- `cursor` + `page_number` both set → 400.
- Stale cursor (different `order_by`) → 400.

## Observability

Three new metrics:

- `authz_check_batch_calls_total{resource_type, cache_state=hit|miss|partial}` — counter.
- `authz_check_batch_size{resource_type}` — histogram of input / miss / output sizes.
- `list_pagination_walk_iterations{endpoint, mode=cursor|legacy}` — histogram. Surfaces deep-page pain in legacy mode and unauthorized-density in cursor mode.

Plus a structured log warning when legacy walk-until-filled crosses 5 DB roundtrips for a single request, so we can tell which clients are stuck on the old API.

Metric names follow whatever naming convention the existing repo uses; verify and align during Phase 2.

## Rollout

**Phase 1 — `agentex-auth` primitive (dead-code ship).** Land `check_batch` gateway method, SGP adapter implementation, `/v1/authz/check_batch` HTTP endpoint. No agentex consumer yet. Deploy independently.

**Phase 2 — `agentex` backend primitives (dead-code ship).** Land `AuthorizationService.check_batch`, `AgentexAuthorizationProxy.check_batch`, `AuthorizationFilter` + `DAuthorizationFilter`, cursor encoding/decoding helpers, and the keyset repository method. No route changes. Tests cover all new units.

**Phase 3 — migrate `GET /tasks`.** Switch the route from `DAuthorizedResourceIds` to `DAuthorizationFilter`. Add `cursor` query param, add `X-Next-Cursor` response header, route to cursor or legacy use case. Both modes ship together — no feature flag needed; the surface is small enough to test in staging directly.

**Phase 4 — verify in staging.** Issue list calls with > 999 owned tasks. Verify both cursor and legacy paths return more than 999 across multiple calls. Verify the `X-Next-Cursor` contract end-to-end. Watch the new metrics for one full sync cycle.

**Phase 5 — generalize and clean up.** Apply the same pattern to other `DAuthorizedResourceIds` consumers (`agents`, `deployments`, `schedules`, `messages`, etc.) one at a time. Each migration is a small, mechanical PR using the same primitives. After all consumers migrate, delete `DAuthorizedResourceIds`, `AuthorizationService.list_resources`, the proxy `list_resources` method, and the `/v1/authz/search` endpoint on `agentex-auth`.

Each phase is independently shippable and rollback-safe. Phases 1 and 2 ship dead code; Phase 3 is the user-visible turn-on for one route; Phase 5 is mechanical fan-out.

## Open questions

- Metric naming convention — match the existing repo pattern. Verify in Phase 2.
- Walk-until-filled chunk size (currently `max(limit, 100)`) — picked by intuition; tune from metrics after Phase 4.
- Whether to keep `AuthorizationService._bypass()` as a private alias after promoting `is_bypassed()`. Either way, internal callers migrate in Phase 2.
