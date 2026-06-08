"""AGX1-327 — State list/get delegates read to parent task view.

States do not have their own authz resource. Reads must collapse through the
parent task: list filters to states whose tasks are readable, and direct get
returns 404 when the caller cannot view the parent task.
"""

import pytest

TASK_RESOURCE_TYPE = "task"


@pytest.mark.e2e
class TestStateListGet:
    def test_list_filters_to_viewable_tasks_and_get_denied_state_returns_404(
        self,
        task_parent_agent,
        create_task,
        create_state,
        agentex_client_b,
        authz_client,
        cleanup,
        user_a,
        user_b,
    ):
        agent_id, _ = task_parent_agent
        visible_task_id, _ = create_task(agent_id)
        hidden_task_id, _ = create_task(agent_id)
        visible_state_id = create_state(
            visible_task_id,
            agent_id,
            {"visibility": "visible"},
        )
        hidden_state_id = create_state(
            hidden_task_id,
            agent_id,
            {"visibility": "hidden"},
        )

        grant_resp = authz_client.grant_access(
            resource_type=TASK_RESOURCE_TYPE,
            resource_id=visible_task_id,
            subject_id=user_a.identity_id,
            subject_type=user_a.subject_type,
            relation="viewer",
            grantee_id=user_b.identity_id,
            grantee_type=user_b.subject_type,
        )
        assert grant_resp.status_code in (200, 204), grant_resp.text

        cleanup.add(
            f"revoke user_b viewer on task {visible_task_id}",
            lambda: authz_client.revoke_access(
                resource_type=TASK_RESOURCE_TYPE,
                resource_id=visible_task_id,
                subject_id=user_a.identity_id,
                subject_type=user_a.subject_type,
                relation="viewer",
                grantee_id=user_b.identity_id,
                grantee_type=user_b.subject_type,
            ),
        )

        assert authz_client.check_permission_bool(
            user_b.identity_id,
            TASK_RESOURCE_TYPE,
            visible_task_id,
            "read",
            user_b.subject_type,
        )
        assert not authz_client.check_permission_bool(
            user_b.identity_id,
            TASK_RESOURCE_TYPE,
            hidden_task_id,
            "read",
            user_b.subject_type,
        )

        list_resp = agentex_client_b.list_states(agent_id=agent_id)
        assert list_resp.status_code == 200, list_resp.text
        listed_ids = [state["id"] for state in list_resp.json()]
        assert visible_state_id in listed_ids
        assert (
            hidden_state_id not in listed_ids
        ), f"user_b saw state for non-viewable task in list: {listed_ids}"

        visible_get = agentex_client_b.get_state(visible_state_id)
        assert visible_get.status_code == 200, visible_get.text
        assert visible_get.json()["id"] == visible_state_id

        hidden_get = agentex_client_b.get_state(hidden_state_id)
        assert hidden_get.status_code == 404, (
            f"expected 404 for state whose parent task is not viewable, "
            f"got {hidden_get.status_code}: {hidden_get.text}"
        )
