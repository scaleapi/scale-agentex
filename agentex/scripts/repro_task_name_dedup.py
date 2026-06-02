#!/usr/bin/env python3
"""
Live reproduction of the task/create get-or-create-by-name behavior, against a
running AgentEx backend and a real registered agent.

This mirrors how an orchestrator delegates to a sub-agent: it issues a
``task/create`` RPC with a task ``name`` derived from the prompt's first line
(``prompt.split("\\n")[0][:80]``) and then sends the prompt. When two
delegations produce the same derived name, the second ``task/create`` does NOT
create a new task -- it silently returns the first task (same id, same prior
state), and the new call's ``params`` overwrite the existing row's params.

The HTTP calls below are the exact wire equivalent of the SDK call BP uses:

    await client.agents.rpc_by_name(
        agent_name=agent_name,
        method="task/create",
        params={"name": display_name, "params": {...}},
    )

Prerequisites
-------------
A running backend (default http://localhost:5003), e.g. ``./dev.sh`` from the
repo root or ``make dev`` from ``agentex/``.

Usage
-----
    uv run python agentex/scripts/repro_task_name_dedup.py
    # or against a different host:
    AGENTEX_BASE_URL=http://localhost:5003 uv run python agentex/scripts/repro_task_name_dedup.py

A SYNC agent is registered for the repro so ``task/create`` does not need a live
sub-agent process to forward to. The get-or-create-by-name step runs identically
for ASYNC agents (it happens before any forward), so the dedup behavior shown
here is exactly what an ASYNC sub-agent delegation hits.
"""

import os
import sys
import time
import uuid

import httpx

BASE_URL = os.environ.get("AGENTEX_BASE_URL", "http://localhost:5003")


def _rpc(client: httpx.Client, agent_name: str, method: str, params: dict) -> dict:
    """Wire-equivalent of ``client.agents.rpc_by_name(...)``."""
    resp = client.post(
        f"/agents/name/{agent_name}/rpc",
        json={
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        },
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("error"):
        raise RuntimeError(f"RPC {method} returned error: {body['error']}")
    return body["result"]


def _bp_display_name(prompt: str) -> str:
    """The exact derivation BP uses in delegate_activity.py."""
    return prompt.split("\n")[0][:80]


def main() -> int:
    agent_name = f"dedup-repro-{uuid.uuid4().hex[:8]}"

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        # 1. Register a real agent (idempotent get-or-create on the backend).
        client.post(
            "/agents/register",
            json={
                "name": agent_name,
                "description": "Ephemeral agent for task-name dedup repro",
                "acp_url": "http://localhost:9",  # unused: sync agents don't forward
                "acp_type": "sync",
            },
        ).raise_for_status()
        print(f"Registered agent: {agent_name}\n")

        # 2. Two DIFFERENT prompts that happen to share the same first line.
        #    BP derives the task name from prompt.split("\n")[0][:80], so both
        #    collapse to the same task name -> the collision an orchestrator hits.
        prompt_a = (
            "Summarize the quarterly report\n\nFocus on revenue and churn for region A."
        )
        prompt_b = "Summarize the quarterly report\n\nFocus on headcount and burn for region B."
        assert _bp_display_name(prompt_a) == _bp_display_name(prompt_b)
        display_name = _bp_display_name(prompt_a)
        print(f"Derived task name for both prompts: {display_name!r}\n")

        first = _rpc(
            client,
            agent_name,
            "task/create",
            {"name": display_name, "params": {"prompt": prompt_a}},
        )
        print(
            f"Delegation #1 -> task id: {first['id']}  created_at: {first['created_at']}"
        )

        time.sleep(0.05)

        second = _rpc(
            client,
            agent_name,
            "task/create",
            {"name": display_name, "params": {"prompt": prompt_b}},
        )
        print(
            f"Delegation #2 -> task id: {second['id']}  created_at: {second['created_at']}"
        )

        # 3. A genuinely unique name returns a brand-new task.
        unique = _rpc(
            client,
            agent_name,
            "task/create",
            {
                "name": f"{display_name} {uuid.uuid4().hex[:6]}",
                "params": {"prompt": prompt_b},
            },
        )
        print(f"Delegation #3 (unique name) -> task id: {unique['id']}")

        # 4. The workaround: omit `name` entirely. `name` is optional at the RPC
        #    layer, and NULL names are exempt from the unique constraint, so every
        #    name-less task/create returns a brand-new task with clean history.
        noname_1 = _rpc(
            client, agent_name, "task/create", {"params": {"prompt": prompt_a}}
        )
        noname_2 = _rpc(
            client, agent_name, "task/create", {"params": {"prompt": prompt_b}}
        )
        print(
            f"Delegation #4 (no name) -> task id: {noname_1['id']}  name: {noname_1['name']!r}"
        )
        print(
            f"Delegation #5 (no name) -> task id: {noname_2['id']}  name: {noname_2['name']!r}\n"
        )

        # ---- Findings ----
        reused = second["id"] == first["id"]
        stale = second["created_at"] == first["created_at"]
        new_when_unique = unique["id"] != first["id"]
        noname_accepted = noname_1["name"] is None and noname_2["name"] is None
        noname_always_new = noname_1["id"] != noname_2["id"]

        print("Findings:")
        print(f"  same name reused the first task             : {reused}")
        print(
            f"  reused task kept the ORIGINAL created_at     : {stale}  (it's the old row, not a new task)"
        )
        print(f"  second call's params overwrote the row       : {second['params']!r}")
        print(f"  unique name produced a NEW task              : {new_when_unique}")
        print(f"  name is OPTIONAL (omitting it is accepted)   : {noname_accepted}")
        print(f"  no-name task/create is always a NEW task     : {noname_always_new}")

        # Best-effort cleanup of the tasks we created.
        for task_id in {
            first["id"],
            second["id"],
            unique["id"],
            noname_1["id"],
            noname_2["id"],
        }:
            try:
                client.delete(f"/tasks/{task_id}")
            except Exception:
                pass

        ok = (
            reused
            and stale
            and new_when_unique
            and noname_accepted
            and noname_always_new
        )
        print(
            "\nRESULT:",
            "REPRODUCED the dedup footgun (and confirmed name is optional)"
            if ok
            else "did NOT reproduce",
        )
        return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except httpx.HTTPError as e:
        print(f"\nHTTP error talking to {BASE_URL}: {e}", file=sys.stderr)
        print(
            "Is the backend running? Try ./dev.sh (repo root) or make dev (agentex/).",
            file=sys.stderr,
        )
        sys.exit(2)
