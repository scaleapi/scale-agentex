# Manual `agent_api_keys` smoke — pubsec-dev

Copy-paste manual smoke for the `agent_api_keys` routes against
`agentex.sgp-pubsec-dev.scale.com`. **No e2e suite. No venv. Just `curl`.**

Set the four env vars at the top, then paste any case block.

Companion to the automated suite in this directory — same coverage, but
each case is one independent `curl` you can run from any shell.

## Prereqs

- A real pubsec-dev API key (`ssk_is_…`).
- The agentex-compatible `account_id` used for `x-selected-account-id`.
- An existing `agent_id` where you have `api_key.create` permission.
- (Optional) A second user's API key for tenant-isolation cases (15–17).

```bash
export KEY="ssk_is_..."                                  # your api key
export ACCT="69c69407ee5d19e1dce57d57"                   # x-selected-account-id
export AGENT="811a4c69-e86d-46b3-9293-0bc8443f599d"      # parent agent (golden-agent works)
export BASE="https://agentex.sgp-pubsec-dev.scale.com"
H() { echo "-H"; echo "x-api-key: $KEY"; echo "-H"; echo "x-selected-account-id: $ACCT"; }
```

---

## Case 1 — Reachability + auth sanity

Confirm the API is reachable and your headers authenticate. **Expected:**
`200` + JSON array of agents.

```bash
curl -sS -w "\nHTTP %{http_code}\n" $(H) "$BASE/agents"
```

✅ Pass if `HTTP 200` and you see agents.

---

## Case 2 — OpenAPI shape

Confirm `agent_api_key` routes are published. **Expected:** five paths
under `/agent_api_keys`.

```bash
curl -sS "$BASE/openapi.json" | python3 -c "
import json,sys
print('\n'.join(sorted(p for p in json.load(sys.stdin)['paths'] if 'api_key' in p)))
"
```

✅ Pass if you see `/agent_api_keys`, `/agent_api_keys/{id}`,
`/agent_api_keys/name/{name}`, `/agent_api_keys/name/{api_key_name}`.

---

## Case 3 — Create happy path

Mint an api_key. **Expected:** `200` with `id` + `api_key` in body.

```bash
NAME="manual-smoke-$(date +%s)"
RESP=$(curl -sS -w "\nHTTP %{http_code}" -X POST $(H) \
  -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"$AGENT\",\"name\":\"$NAME\",\"api_key_type\":\"external\"}" \
  "$BASE/agent_api_keys")
echo "$RESP"
export KID=$(echo "$RESP" | head -n -1 | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
echo "KID=$KID"
```

✅ Pass if `HTTP 200` and `KID` is a UUID. Save `$KID` for later cases.

---

## Case 4 — Validation: enum is lowercase

Payload uses `EXTERNAL` (uppercase). **Expected:** `422` rejection.

```bash
curl -sS -w "\nHTTP %{http_code}\n" -X POST $(H) \
  -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"$AGENT\",\"name\":\"x\",\"api_key_type\":\"EXTERNAL\"}" \
  "$BASE/agent_api_keys"
```

✅ Pass if `HTTP 422`.

---

## Case 5 — Validation: requires id OR name

Payload omits both `agent_id` and `agent_name`. **Expected:** `400`.

```bash
curl -sS -w "\nHTTP %{http_code}\n" -X POST $(H) \
  -H "Content-Type: application/json" \
  -d '{"name":"x","api_key_type":"external"}' \
  "$BASE/agent_api_keys"
```

✅ Pass if `HTTP 400`.

---

## Case 6 — Validation: rejects both id AND name

Payload includes both. **Expected:** `400`.

```bash
curl -sS -w "\nHTTP %{http_code}\n" -X POST $(H) \
  -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"$AGENT\",\"agent_name\":\"some-name\",\"name\":\"x\",\"api_key_type\":\"external\"}" \
  "$BASE/agent_api_keys"
```

✅ Pass if `HTTP 400`.

---

## Case 7 — Duplicate-name conflict

Create the same `(agent_id, name, type)` twice. **Expected:** second call
returns `409`.

```bash
DUP="dup-$(date +%s)"
for i in 1 2; do
  echo "--- attempt $i ---"
  curl -sS -w "\nHTTP %{http_code}\n" -X POST $(H) \
    -H "Content-Type: application/json" \
    -d "{\"agent_id\":\"$AGENT\",\"name\":\"$DUP\",\"api_key_type\":\"external\"}" \
    "$BASE/agent_api_keys"
done
```

✅ Pass if attempt 1 = `200`, attempt 2 = `409`.

---

## Case 8 — Missing auth

No headers. **Expected:** `401`.

```bash
curl -sS -w "\nHTTP %{http_code}\n" "$BASE/agent_api_keys/anything"
```

✅ Pass if `HTTP 401`.

---

## Case 9 — Bogus API key

Garbage `x-api-key`. **Expected:** `401`.

```bash
curl -sS -w "\nHTTP %{http_code}\n" \
  -H "x-api-key: bogus" -H "x-selected-account-id: $ACCT" \
  "$BASE/agents"
```

✅ Pass if `HTTP 401`.

---

## Case 10 — Owner GET by id

Read the key you just created (Case 3). **Expected (healthy env):** `200`
with the same id. **Today on pubsec-dev:** `422` (agentex-auth is still
configured with `AUTH_PROVIDER=sgp`, so the route-level FGAC check routes
to legacy SGP-authz which doesn't know about `api_key`).

```bash
curl -sS -w "\nHTTP %{http_code}\n" $(H) "$BASE/agent_api_keys/$KID"
```

Today: ❌ `422`. After the `AUTH_PROVIDER=spark` rollout: ✅ `200`.

---

## Case 11 — Owner GET by name

Same row, looked up by name. **Expected (healthy):** `200`.
**Today:** `422`.

```bash
curl -sS -w "\nHTTP %{http_code}\n" $(H) \
  "$BASE/agent_api_keys/name/$NAME?agent_id=$AGENT&api_key_type=external"
```

---

## Case 12 — Owner LIST under agent

Confirm the list includes `$KID`. **Expected (healthy):** `200` + array
containing it. **Today:** `422`.

```bash
curl -sS -w "\nHTTP %{http_code}\n" $(H) \
  "$BASE/agent_api_keys?agent_id=$AGENT" | python3 -c "
import json, sys, os
body = sys.stdin.read()
try:
    arr = json.loads(body)
    print('count:', len(arr))
    print('contains target:', any(k.get('id') == os.environ['KID'] for k in arr))
except Exception:
    print(body)
"
```

---

## Case 13 — GET nonexistent

Read a UUID that doesn't exist. **Expected (healthy):** `404`.
**Today:** likely `422` (same Gap-1 wrap).

```bash
curl -sS -w "\nHTTP %{http_code}\n" $(H) \
  "$BASE/agent_api_keys/00000000-0000-0000-0000-000000000000"
```

---

## Case 14 — Owner DELETE

Delete the key, then confirm it's gone. **Expected (healthy):** `200`,
then `404` on re-read. **Today:** both calls return `422`.

```bash
curl -sS -w "\nHTTP %{http_code}\n" -X DELETE $(H) "$BASE/agent_api_keys/$KID"
echo "--- re-fetch ---"
curl -sS -w "\nHTTP %{http_code}\n" $(H) "$BASE/agent_api_keys/$KID"
```

---

## Case 15 — Non-owner GET → 404 (no existence leak)

Requires `KEY_B` for a second user in the same tenant.

```bash
export KEY_B="ssk_is_..."   # second user's key
curl -sS -w "\nHTTP %{http_code}\n" \
  -H "x-api-key: $KEY_B" -H "x-selected-account-id: $ACCT" \
  "$BASE/agent_api_keys/$KID"
```

✅ Pass if `HTTP 404`. **Critical:** must NOT be `403` (leaks existence).

---

## Case 16 — Non-owner LIST is filtered

Requires `KEY_B`.

```bash
curl -sS -H "x-api-key: $KEY_B" -H "x-selected-account-id: $ACCT" \
  "$BASE/agent_api_keys?agent_id=$AGENT" | python3 -c "
import json, sys, os
body = sys.stdin.read()
try:
    arr = json.loads(body)
    print('user_b list count:', len(arr))
    print('contains user_a key:', any(k.get('id') == os.environ['KID'] for k in arr))
except Exception:
    print(body)
"
```

✅ Pass if `contains user_a key: False`.

---

## Case 17 — Non-owner DELETE preserves row

Requires `KEY_B`.

```bash
# user_b attempts delete
curl -sS -w "\nHTTP %{http_code}\n" -X DELETE \
  -H "x-api-key: $KEY_B" -H "x-selected-account-id: $ACCT" \
  "$BASE/agent_api_keys/$KID"
# user_a re-fetches
curl -sS -w "\nHTTP %{http_code}\n" $(H) "$BASE/agent_api_keys/$KID"
```

✅ Pass if user_b's call = `404` AND user_a's re-fetch = `200`
(row not deleted).

---

## Quick scorecard

| | Today on pubsec-dev | After `AUTH_PROVIDER=spark` rollout |
|---|---|---|
| **Cases 1–9** — HTTP + validation | ✅ All pass | ✅ Still pass |
| **Cases 10–14** — owner FGAC paths | ❌ All `422` | ✅ All pass |
| **Cases 15–17** — tenant isolation | ❌ Same `422` blocker; also needs second user | ✅ Pass with `KEY_B` |

**Run Cases 1–9 today.** They confirm the route layer is healthy and the
contract (validation, auth, conflict handling) holds.

**Cases 10–17 are the rollout-verification kit.** Re-run them after the
`AUTH_PROVIDER=spark` flip on pubsec-dev's `agentex-auth` deployment to
confirm the FGAC dual-write works end-to-end.

## Background: the rollout blocker

Pubsec-dev's `agentex-auth` deployment has `AUTH_PROVIDER=sgp`. Every
`register_resource` / `deregister_resource` call from scale-agentex's
dual-write code lands on legacy SGP-authz instead of `spark-authz`
(which IS deployed in the cluster — `ns/spark`, `svc/spark-authz`, ports
50052/8090 — verified reachable via port-forward + `/healthz` returning
`SERVING`).

To unblock: redeploy `agentex-auth` in pubsec-dev with
`AUTH_PROVIDER=spark` plus
`SPARK_AUTHZ_GRPC_TARGET=spark-authz.spark.svc.cluster.local:50052`. No
new infra needed — just a value change in the Helm chart that
`sgp-system-manager` renders for pubsec-dev.

The Jinja template that hardcodes this lives at
`sgp/services/sgp-system-manager/sgp_system_manager/packs/agentex-auth/values.yaml.jinja2:20`.
