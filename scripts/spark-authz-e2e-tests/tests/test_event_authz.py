"""AGX1-331 — Events: read-only, delegated to parent ``agent.read``.

Scope from the ticket:

  > Event get/list delegated to parent agent view (read-only): no agent view,
  > 404 on get and filtered/empty list

Events have no public ``POST`` route in scale-agentex — they're emitted by
ACP streaming and persisted by the worker. So the happy-path side of this
suite ("with view, event is returned") would require either (a) direct DB
seeding, breaking the black-box property, or (b) running an actual agent.
Neither belongs in an e2e PR scoped to authz checks.

What we CAN black-box, and what the ticket asks for: the denied-path
behavior on both routes. The "with view" happy path is left as a skipped
test below with a clear reason so that whoever later wires up an event-
seeding harness can flip the skip to a real assertion.
"""

import pytest
from helpers.factories import unique_agent_name


@pytest.mark.e2e
class TestEventAuthz:
    def test_get_event_nonexistent_returns_404(self, agentex_client_a):
        """A get on a nonexistent event id 404s before any authz fires.

        Pure sanity for the route shape: the use case raises
        ``ItemDoesNotExist`` on the repo lookup; the parent-agent check
        never runs.
        """
        resp = agentex_client_a.get_event("00000000-0000-0000-0000-000000000000")
        assert (
            resp.status_code == 404
        ), f"expected 404 on nonexistent event id, got {resp.status_code}: {resp.text}"

    def test_list_events_without_agent_view_returns_404(
        self,
        parent_agent,
        agentex_client_b,
    ):
        """user_b lacks ``read`` on user_a's agent → ``DAuthorizedQuery``
        denies the call → collapsed to 404 (not 403) so the agent's
        existence isn't leakable.
        """
        agent_id, _ = parent_agent
        # Use an arbitrary task id; the DAuthorizedQuery on agent_id fires
        # first and short-circuits before the task is even looked at.
        denied = agentex_client_b.list_events(
            task_id="00000000-0000-0000-0000-000000000001",
            agent_id=agent_id,
        )
        assert denied.status_code == 404, (
            f"expected 404 (collapsed from denied), got {denied.status_code}: "
            f"{denied.text}"
        )

    def test_list_events_denied_on_both_query_params_returns_404(
        self,
        agentex_client_b,
    ):
        """When user_b is denied on both ``task_id`` and ``agent_id``, the
        route collapses to 404. This verifies the route is gated end-to-end
        but does NOT isolate which gate fired: FastAPI evaluates the
        ``task_id`` ``Depends`` first, so the ``agent_id`` gate never
        executes here. Isolating each gate independently would require
        granting one resource but not the other in SpiceDB, which depends
        on a reachable spark-authz (see ``authz_client`` skip behavior).
        """
        resp = agentex_client_b.list_events(
            task_id="00000000-0000-0000-0000-000000000002",
            agent_id="00000000-0000-0000-0000-000000000003",
        )
        assert resp.status_code == 404, (
            f"expected 404 (collapsed from denied), got {resp.status_code}: "
            f"{resp.text}"
        )

    @pytest.mark.skip(
        reason=(
            "Black-box event seeding isn't possible — no public POST /events "
            "and the ACP-stream path requires running an agent. Wire this up "
            "once a test-only seeding helper exists (Linear: TODO follow-up)."
        )
    )
    def test_get_event_with_view_returns_200(self, create_agent, agentex_client_a):
        """Happy path: user_a has ``read`` on the parent agent → ``GET
        /events/{id}`` returns 200 and the event payload.
        """
        agent_id, _ = create_agent(name=unique_agent_name(prefix="agx1-331-happy"))
        # event_id = <seed_event_via_some_helper>(agent_id=agent_id)
        # resp = agentex_client_a.get_event(event_id)
        # assert resp.status_code == 200
        # assert resp.json()["agent_id"] == agent_id
        pytest.fail("seeding helper not implemented")
