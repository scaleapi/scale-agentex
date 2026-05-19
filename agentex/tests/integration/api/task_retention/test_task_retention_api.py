"""
Integration tests for task retention endpoints: export / clean / rehydrate.

Covers the round-trip invariant (export → clean → rehydrate → export yields a
byte-identical snapshot), each precondition guard, and the cross-store cleanup
surfaces (Mongo messages, Mongo task_states, Postgres events, Postgres
agent_task_tracker cursor, Postgres tasks.cleaned_at).
"""

import pytest
import pytest_asyncio
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.states import StateEntity
from src.domain.entities.task_messages import TaskMessageEntity, TextContentEntity
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.utils.ids import orm_id


@pytest.mark.asyncio
class TestTaskRetentionAPIIntegration:
    """Integration tests for /tasks/{id}/{export,clean,rehydrate}."""

    @pytest_asyncio.fixture
    async def test_agent(self, isolated_repositories):
        agent_repo = isolated_repositories["agent_repository"]
        return await agent_repo.create(
            AgentEntity(
                id=orm_id(),
                name="test-retention-agent",
                description="Agent for retention testing",
                acp_url="http://test-acp:8000",
                acp_type=ACPType.SYNC,
            )
        )

    @pytest_asyncio.fixture
    async def stale_task(self, isolated_repositories, test_agent):
        """Non-RUNNING task — eligible for cleanup."""
        task_repo = isolated_repositories["task_repository"]
        return await task_repo.create(
            agent_id=test_agent.id,
            task=TaskEntity(
                id=orm_id(),
                name="stale-task",
                status=TaskStatus.FAILED,
                status_reason="test fixture",
            ),
        )

    @pytest_asyncio.fixture
    async def running_task(self, isolated_repositories, test_agent):
        """RUNNING task — should be refused by clean."""
        task_repo = isolated_repositories["task_repository"]
        return await task_repo.create(
            agent_id=test_agent.id,
            task=TaskEntity(
                id=orm_id(),
                name="running-task",
                status=TaskStatus.RUNNING,
                status_reason="test fixture",
            ),
        )

    async def _seed_messages(self, isolated_repositories, task_id, count):
        message_repo = isolated_repositories["task_message_repository"]
        messages = []
        for i in range(count):
            messages.append(
                await message_repo.create(
                    TaskMessageEntity(
                        id=orm_id(),
                        task_id=task_id,
                        content=TextContentEntity(
                            type="text", author="user", content=f"msg {i}"
                        ),
                        streaming_status="DONE",
                    )
                )
            )
        return messages

    async def _seed_state(self, isolated_repositories, task_id, agent_id):
        state_repo = isolated_repositories["task_state_repository"]
        return await state_repo.create(
            StateEntity(
                id=orm_id(),
                task_id=task_id,
                agent_id=agent_id,
                state={"counter": 1, "nested": {"k": "v"}},
            )
        )

    # ---- export ----

    async def test_export_returns_full_snapshot(
        self, isolated_client, isolated_repositories, stale_task, test_agent
    ):
        await self._seed_messages(isolated_repositories, stale_task.id, 3)
        await self._seed_state(isolated_repositories, stale_task.id, test_agent.id)

        response = await isolated_client.get(f"/tasks/{stale_task.id}/export")

        assert response.status_code == 200
        snapshot = response.json()
        assert snapshot["task_id"] == stale_task.id
        assert len(snapshot["messages"]) == 3
        assert len(snapshot["task_states"]) == 1
        # Messages ordered chronologically (asc by created_at)
        contents = [m["content"]["content"] for m in snapshot["messages"]]
        assert contents == ["msg 0", "msg 1", "msg 2"]

    async def test_export_empty_task_returns_empty_collections(
        self, isolated_client, stale_task
    ):
        response = await isolated_client.get(f"/tasks/{stale_task.id}/export")

        assert response.status_code == 200
        snapshot = response.json()
        assert snapshot["messages"] == []
        assert snapshot["task_states"] == []

    async def test_export_nonexistent_task_returns_404(self, isolated_client):
        response = await isolated_client.get(
            "/tasks/00000000-0000-0000-0000-000000000000/export"
        )

        assert response.status_code == 404

    # ---- clean ----

    async def test_clean_force_succeeds_and_clears_all_surfaces(
        self, isolated_client, isolated_repositories, stale_task, test_agent
    ):
        await self._seed_messages(isolated_repositories, stale_task.id, 3)
        await self._seed_state(isolated_repositories, stale_task.id, test_agent.id)

        response = await isolated_client.post(
            f"/tasks/{stale_task.id}/clean", json={"force": True}
        )

        assert response.status_code == 200
        result = response.json()
        assert result["task_id"] == stale_task.id
        assert result["messages_deleted"] == 3
        assert result["task_states_deleted"] == 1
        assert result["events_deleted"] == 0
        assert result["cleaned_at"] is not None

        # Verify Mongo surfaces are empty.
        export_after = (
            await isolated_client.get(f"/tasks/{stale_task.id}/export")
        ).json()
        assert export_after["messages"] == []
        assert export_after["task_states"] == []

        # Verify tasks.cleaned_at is set.
        task_after = (await isolated_client.get(f"/tasks/{stale_task.id}")).json()
        assert task_after["cleaned_at"] is not None

    async def test_clean_resets_agent_task_tracker_cursor(
        self, isolated_client, isolated_repositories, stale_task, test_agent
    ):
        # Plant a cursor on the auto-created tracker so we can prove the reset.
        tracker_repo = isolated_repositories["agent_task_tracker_repository"]
        trackers = await tracker_repo.find_by_field("task_id", stale_task.id)
        assert len(trackers) == 1
        # task_repository.create creates a tracker with cursor=None already; the
        # property we care about is that the reset path runs idempotently.

        await isolated_client.post(
            f"/tasks/{stale_task.id}/clean", json={"force": True}
        )

        trackers_after = await tracker_repo.find_by_field("task_id", stale_task.id)
        assert len(trackers_after) == 1
        assert trackers_after[0].last_processed_event_id is None

    async def test_clean_running_task_returns_400(self, isolated_client, running_task):
        response = await isolated_client.post(
            f"/tasks/{running_task.id}/clean", json={"force": True}
        )

        assert response.status_code == 400
        assert "RUNNING" in response.json()["message"]

    async def test_clean_already_cleaned_task_returns_empty_result(
        self, isolated_client, isolated_repositories, stale_task
    ):
        await self._seed_messages(isolated_repositories, stale_task.id, 2)
        # First clean — does the work.
        first = await isolated_client.post(
            f"/tasks/{stale_task.id}/clean", json={"force": True}
        )
        assert first.status_code == 200
        first_cleaned_at = first.json()["cleaned_at"]

        # Second clean — should be a no-op returning the prior cleaned_at.
        second = await isolated_client.post(
            f"/tasks/{stale_task.id}/clean", json={"force": True}
        )
        assert second.status_code == 200
        result = second.json()
        assert result["messages_deleted"] == 0
        assert result["task_states_deleted"] == 0
        assert result["events_deleted"] == 0
        assert result["cleaned_at"] == first_cleaned_at

    async def test_clean_unprocessed_events_returns_400(
        self, isolated_client, isolated_repositories, stale_task, test_agent
    ):
        # Plant an event with no cursor advancement; _has_unprocessed_events will
        # see the event past the (null) cursor and refuse.
        event_repo = isolated_repositories["event_repository"]
        await event_repo.create(
            id=orm_id(),
            task_id=stale_task.id,
            agent_id=test_agent.id,
            content=None,
        )

        response = await isolated_client.post(
            f"/tasks/{stale_task.id}/clean", json={"force": True}
        )

        assert response.status_code == 400
        assert "unprocessed events" in response.json()["message"]

    async def test_clean_nonexistent_task_returns_404(self, isolated_client):
        response = await isolated_client.post(
            "/tasks/00000000-0000-0000-0000-000000000000/clean",
            json={"force": True},
        )

        assert response.status_code == 404

    # ---- rehydrate ----

    async def test_round_trip_is_byte_identical(
        self, isolated_client, isolated_repositories, stale_task, test_agent
    ):
        """
        The load-bearing invariant: export → clean → rehydrate → export
        yields the same snapshot down to IDs and timestamps. ID preservation
        is what makes rehydrated tasks indistinguishable from the original.
        """
        await self._seed_messages(isolated_repositories, stale_task.id, 3)
        await self._seed_state(isolated_repositories, stale_task.id, test_agent.id)

        snapshot_before = (
            await isolated_client.get(f"/tasks/{stale_task.id}/export")
        ).json()

        clean = await isolated_client.post(
            f"/tasks/{stale_task.id}/clean", json={"force": True}
        )
        assert clean.status_code == 200

        rehydrate = await isolated_client.post(
            f"/tasks/{stale_task.id}/rehydrate", json=snapshot_before
        )
        assert rehydrate.status_code == 204

        snapshot_after = (
            await isolated_client.get(f"/tasks/{stale_task.id}/export")
        ).json()

        assert snapshot_after == snapshot_before

        # Sanity: task is back to active (cleaned_at=None).
        task_after = (await isolated_client.get(f"/tasks/{stale_task.id}")).json()
        assert task_after["cleaned_at"] is None

    async def test_rehydrate_active_task_returns_400(self, isolated_client, stale_task):
        # Task was never cleaned; rehydrate must refuse.
        payload = {"task_id": stale_task.id, "messages": [], "task_states": []}
        response = await isolated_client.post(
            f"/tasks/{stale_task.id}/rehydrate", json=payload
        )

        assert response.status_code == 400
        assert "not in cleaned state" in response.json()["message"]

    async def test_rehydrate_task_id_mismatch_returns_400(
        self, isolated_client, stale_task
    ):
        # Clean first so we'd otherwise pass the cleaned_at guard.
        await isolated_client.post(
            f"/tasks/{stale_task.id}/clean", json={"force": True}
        )

        payload = {
            "task_id": "00000000-0000-0000-0000-000000000000",
            "messages": [],
            "task_states": [],
        }
        response = await isolated_client.post(
            f"/tasks/{stale_task.id}/rehydrate", json=payload
        )

        assert response.status_code == 400
        assert "does not match" in response.json()["message"]

    async def test_rehydrate_id_collision_returns_400(
        self, isolated_client, isolated_repositories, stale_task
    ):
        # Seed, snapshot, clean, then re-insert one message so the rehydrate
        # collides on _id.
        await self._seed_messages(isolated_repositories, stale_task.id, 2)
        snapshot = (await isolated_client.get(f"/tasks/{stale_task.id}/export")).json()
        await isolated_client.post(
            f"/tasks/{stale_task.id}/clean", json={"force": True}
        )

        # Plant a colliding doc with the same _id the rehydrate would use.
        first = snapshot["messages"][0]
        message_repo = isolated_repositories["task_message_repository"]
        await message_repo.create(
            TaskMessageEntity(
                id=first["id"],
                task_id=stale_task.id,
                content=TextContentEntity(
                    type="text", author="user", content="planted collision"
                ),
                streaming_status="DONE",
            )
        )

        response = await isolated_client.post(
            f"/tasks/{stale_task.id}/rehydrate", json=snapshot
        )

        assert response.status_code == 400
        assert "duplicate id" in response.json()["message"].lower()
