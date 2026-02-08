"""
Integration tests for the checkpoint repository.

Tests the CheckpointRepository against a real PostgreSQL database to validate
that our reimplementation of the LangGraph checkpoint storage operations
(get_tuple, put, put_writes, list_checkpoints, delete_thread) works correctly.
"""

import pytest


@pytest.mark.asyncio
class TestCheckpointRepository:
    """Integration tests for CheckpointRepository CRUD operations."""

    # ── put + get_tuple round-trip ──

    async def test_put_and_get_tuple(self, isolated_repositories):
        """Test basic round-trip: put a checkpoint then get it back."""
        repo = isolated_repositories["checkpoint_repository"]

        checkpoint_data = {
            "id": "cp-1",
            "v": 4,
            "channel_values": {"counter": 42},
            "channel_versions": {"messages": "00000001.123"},
        }
        metadata = {"source": "input", "step": 1, "writes": {}}
        blobs = [
            {
                "channel": "messages",
                "version": "00000001.123",
                "type": "json",
                "blob": b'["hello"]',
            },
        ]

        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint=checkpoint_data,
            metadata=metadata,
            blobs=blobs,
        )

        result = await repo.get_tuple(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
        )

        assert result is not None
        assert result["thread_id"] == "thread-1"
        assert result["checkpoint_ns"] == ""
        assert result["checkpoint_id"] == "cp-1"
        assert result["parent_checkpoint_id"] is None
        assert result["checkpoint"] == checkpoint_data
        assert result["metadata"] == metadata
        assert len(result["blobs"]) == 1
        assert result["blobs"][0]["channel"] == "messages"
        assert result["blobs"][0]["type"] == "json"
        assert bytes(result["blobs"][0]["blob"]) == b'["hello"]'

    async def test_put_updates_existing_checkpoint(self, isolated_repositories):
        """Test that putting a checkpoint with same PK upserts (updates)."""
        repo = isolated_repositories["checkpoint_repository"]

        original = {"id": "cp-1", "v": 4, "channel_values": {"counter": 1}}
        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint=original,
            metadata={"step": 1},
            blobs=[],
        )

        updated = {"id": "cp-1", "v": 4, "channel_values": {"counter": 99}}
        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint=updated,
            metadata={"step": 2},
            blobs=[],
        )

        result = await repo.get_tuple(
            thread_id="thread-1", checkpoint_ns="", checkpoint_id="cp-1"
        )
        assert result is not None
        assert result["checkpoint"]["channel_values"]["counter"] == 99
        assert result["metadata"]["step"] == 2

    # ── get_tuple: latest checkpoint ──

    async def test_get_tuple_latest(self, isolated_repositories):
        """Test that get_tuple without checkpoint_id returns the latest."""
        repo = isolated_repositories["checkpoint_repository"]

        for cp_id in ["cp-1", "cp-2", "cp-3"]:
            await repo.put(
                thread_id="thread-1",
                checkpoint_ns="",
                checkpoint_id=cp_id,
                parent_checkpoint_id=None,
                checkpoint={"id": cp_id},
                metadata={},
                blobs=[],
            )

        result = await repo.get_tuple(thread_id="thread-1", checkpoint_ns="")
        assert result is not None
        # "cp-3" is lexicographically greatest → latest
        assert result["checkpoint_id"] == "cp-3"

    async def test_get_tuple_not_found(self, isolated_repositories):
        """Test that get_tuple returns None for non-existent checkpoint."""
        repo = isolated_repositories["checkpoint_repository"]

        result = await repo.get_tuple(
            thread_id="nonexistent", checkpoint_ns="", checkpoint_id="nope"
        )
        assert result is None

    # ── blobs ──

    async def test_blobs_only_matching_versions_returned(self, isolated_repositories):
        """Test that get_tuple only returns blobs matching channel_versions."""
        repo = isolated_repositories["checkpoint_repository"]

        # Store blobs for two versions
        blobs = [
            {"channel": "messages", "version": "v1", "type": "json", "blob": b"old"},
            {"channel": "messages", "version": "v2", "type": "json", "blob": b"new"},
        ]
        checkpoint = {
            "id": "cp-1",
            "v": 4,
            "channel_versions": {"messages": "v2"},
        }

        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint=checkpoint,
            metadata={},
            blobs=blobs,
        )

        result = await repo.get_tuple(
            thread_id="thread-1", checkpoint_ns="", checkpoint_id="cp-1"
        )
        assert result is not None
        # Should only return v2 blob (matching channel_versions)
        assert len(result["blobs"]) == 1
        assert result["blobs"][0]["version"] == "v2"
        assert bytes(result["blobs"][0]["blob"]) == b"new"

    # ── pending writes ──

    async def test_put_writes_and_get(self, isolated_repositories):
        """Test that writes stored via put_writes appear in get_tuple."""
        repo = isolated_repositories["checkpoint_repository"]

        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint={"id": "cp-1"},
            metadata={},
            blobs=[],
        )

        writes = [
            {
                "task_id": "task-abc",
                "idx": 0,
                "channel": "messages",
                "type": "json",
                "blob": b'{"role": "ai"}',
                "task_path": "",
            },
            {
                "task_id": "task-abc",
                "idx": 1,
                "channel": "output",
                "type": "json",
                "blob": b'"done"',
                "task_path": "",
            },
        ]
        await repo.put_writes(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            writes=writes,
        )

        result = await repo.get_tuple(
            thread_id="thread-1", checkpoint_ns="", checkpoint_id="cp-1"
        )
        assert result is not None
        assert len(result["pending_writes"]) == 2
        assert result["pending_writes"][0]["task_id"] == "task-abc"
        assert result["pending_writes"][0]["channel"] == "messages"
        assert result["pending_writes"][1]["channel"] == "output"

    async def test_put_writes_upsert(self, isolated_repositories):
        """Test that upsert=True updates existing writes."""
        repo = isolated_repositories["checkpoint_repository"]

        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint={"id": "cp-1"},
            metadata={},
            blobs=[],
        )

        original_write = [
            {
                "task_id": "task-1",
                "idx": 0,
                "channel": "messages",
                "type": "json",
                "blob": b"original",
                "task_path": "",
            },
        ]
        await repo.put_writes(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            writes=original_write,
        )

        updated_write = [
            {
                "task_id": "task-1",
                "idx": 0,
                "channel": "messages",
                "type": "json",
                "blob": b"updated",
                "task_path": "",
            },
        ]
        await repo.put_writes(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            writes=updated_write,
            upsert=True,
        )

        result = await repo.get_tuple(
            thread_id="thread-1", checkpoint_ns="", checkpoint_id="cp-1"
        )
        assert result is not None
        assert len(result["pending_writes"]) == 1
        assert bytes(result["pending_writes"][0]["blob"]) == b"updated"

    async def test_put_writes_no_upsert_skips_duplicates(self, isolated_repositories):
        """Test that upsert=False (default) skips conflicting writes."""
        repo = isolated_repositories["checkpoint_repository"]

        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint={"id": "cp-1"},
            metadata={},
            blobs=[],
        )

        write = [
            {
                "task_id": "task-1",
                "idx": 0,
                "channel": "messages",
                "type": "json",
                "blob": b"first",
                "task_path": "",
            },
        ]
        await repo.put_writes(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            writes=write,
        )

        # Try to write again with same PK but different blob — should be skipped
        duplicate_write = [
            {
                "task_id": "task-1",
                "idx": 0,
                "channel": "messages",
                "type": "json",
                "blob": b"second",
                "task_path": "",
            },
        ]
        await repo.put_writes(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            writes=duplicate_write,
            upsert=False,
        )

        result = await repo.get_tuple(
            thread_id="thread-1", checkpoint_ns="", checkpoint_id="cp-1"
        )
        assert result is not None
        assert len(result["pending_writes"]) == 1
        assert bytes(result["pending_writes"][0]["blob"]) == b"first"

    # ── list_checkpoints ──

    async def test_list_checkpoints_basic(self, isolated_repositories):
        """Test listing checkpoints returns them in descending order."""
        repo = isolated_repositories["checkpoint_repository"]

        for cp_id in ["cp-1", "cp-2", "cp-3"]:
            await repo.put(
                thread_id="thread-1",
                checkpoint_ns="",
                checkpoint_id=cp_id,
                parent_checkpoint_id=None,
                checkpoint={"id": cp_id},
                metadata={"source": "loop"},
                blobs=[],
            )

        results = await repo.list_checkpoints(thread_id="thread-1")
        assert len(results) == 3
        # Descending order
        assert results[0]["checkpoint_id"] == "cp-3"
        assert results[1]["checkpoint_id"] == "cp-2"
        assert results[2]["checkpoint_id"] == "cp-1"

    async def test_list_checkpoints_with_metadata_filter(self, isolated_repositories):
        """Test JSONB containment filter (@>) on metadata."""
        repo = isolated_repositories["checkpoint_repository"]

        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint={"id": "cp-1"},
            metadata={"source": "input", "step": 1},
            blobs=[],
        )
        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-2",
            parent_checkpoint_id="cp-1",
            checkpoint={"id": "cp-2"},
            metadata={"source": "loop", "step": 2, "writes": {"foo": "bar"}},
            blobs=[],
        )

        # Filter by source=loop
        results = await repo.list_checkpoints(
            thread_id="thread-1", filter_metadata={"source": "loop"}
        )
        assert len(results) == 1
        assert results[0]["checkpoint_id"] == "cp-2"

        # Filter by source=input
        results = await repo.list_checkpoints(
            thread_id="thread-1", filter_metadata={"source": "input"}
        )
        assert len(results) == 1
        assert results[0]["checkpoint_id"] == "cp-1"

        # Filter that matches nothing
        results = await repo.list_checkpoints(
            thread_id="thread-1", filter_metadata={"source": "nonexistent"}
        )
        assert len(results) == 0

    async def test_list_checkpoints_with_before(self, isolated_repositories):
        """Test before_checkpoint_id pagination."""
        repo = isolated_repositories["checkpoint_repository"]

        for cp_id in ["cp-1", "cp-2", "cp-3"]:
            await repo.put(
                thread_id="thread-1",
                checkpoint_ns="",
                checkpoint_id=cp_id,
                parent_checkpoint_id=None,
                checkpoint={"id": cp_id},
                metadata={},
                blobs=[],
            )

        results = await repo.list_checkpoints(
            thread_id="thread-1", before_checkpoint_id="cp-3"
        )
        assert len(results) == 2
        assert results[0]["checkpoint_id"] == "cp-2"
        assert results[1]["checkpoint_id"] == "cp-1"

    async def test_list_checkpoints_with_limit(self, isolated_repositories):
        """Test limit parameter caps results."""
        repo = isolated_repositories["checkpoint_repository"]

        for cp_id in ["cp-1", "cp-2", "cp-3"]:
            await repo.put(
                thread_id="thread-1",
                checkpoint_ns="",
                checkpoint_id=cp_id,
                parent_checkpoint_id=None,
                checkpoint={"id": cp_id},
                metadata={},
                blobs=[],
            )

        results = await repo.list_checkpoints(thread_id="thread-1", limit=2)
        assert len(results) == 2
        # Should be the two newest
        assert results[0]["checkpoint_id"] == "cp-3"
        assert results[1]["checkpoint_id"] == "cp-2"

    # ── delete_thread ──

    async def test_delete_thread(self, isolated_repositories):
        """Test that delete_thread removes all data for a thread."""
        repo = isolated_repositories["checkpoint_repository"]

        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint={"id": "cp-1", "channel_versions": {"ch": "v1"}},
            metadata={},
            blobs=[{"channel": "ch", "version": "v1", "type": "json", "blob": b"data"}],
        )
        await repo.put_writes(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            writes=[
                {
                    "task_id": "t1",
                    "idx": 0,
                    "channel": "ch",
                    "type": "json",
                    "blob": b"w",
                    "task_path": "",
                }
            ],
        )

        # Verify data exists
        result = await repo.get_tuple(thread_id="thread-1", checkpoint_ns="")
        assert result is not None

        # Delete
        await repo.delete_thread(thread_id="thread-1")

        # Verify everything is gone
        result = await repo.get_tuple(thread_id="thread-1", checkpoint_ns="")
        assert result is None

        results = await repo.list_checkpoints(thread_id="thread-1")
        assert len(results) == 0

    async def test_delete_thread_does_not_affect_other_threads(
        self, isolated_repositories
    ):
        """Test that deleting one thread doesn't affect another."""
        repo = isolated_repositories["checkpoint_repository"]

        for thread_id in ["thread-1", "thread-2"]:
            await repo.put(
                thread_id=thread_id,
                checkpoint_ns="",
                checkpoint_id="cp-1",
                parent_checkpoint_id=None,
                checkpoint={"id": "cp-1"},
                metadata={},
                blobs=[],
            )

        await repo.delete_thread(thread_id="thread-1")

        assert await repo.get_tuple(thread_id="thread-1", checkpoint_ns="") is None
        assert await repo.get_tuple(thread_id="thread-2", checkpoint_ns="") is not None

    # ── isolation ──

    async def test_thread_isolation(self, isolated_repositories):
        """Test that different thread_ids are fully isolated."""
        repo = isolated_repositories["checkpoint_repository"]

        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint={"id": "cp-1", "thread": "1"},
            metadata={},
            blobs=[],
        )
        await repo.put(
            thread_id="thread-2",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint={"id": "cp-1", "thread": "2"},
            metadata={},
            blobs=[],
        )

        r1 = await repo.get_tuple(thread_id="thread-1", checkpoint_ns="")
        r2 = await repo.get_tuple(thread_id="thread-2", checkpoint_ns="")

        assert r1 is not None
        assert r2 is not None
        assert r1["checkpoint"]["thread"] == "1"
        assert r2["checkpoint"]["thread"] == "2"

    async def test_namespace_isolation(self, isolated_repositories):
        """Test that different checkpoint_ns values are isolated."""
        repo = isolated_repositories["checkpoint_repository"]

        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint={"id": "cp-1", "ns": "root"},
            metadata={},
            blobs=[],
        )
        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="inner",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint={"id": "cp-1", "ns": "inner"},
            metadata={},
            blobs=[],
        )

        root = await repo.get_tuple(thread_id="thread-1", checkpoint_ns="")
        inner = await repo.get_tuple(thread_id="thread-1", checkpoint_ns="inner")

        assert root is not None
        assert inner is not None
        assert root["checkpoint"]["ns"] == "root"
        assert inner["checkpoint"]["ns"] == "inner"

    async def test_list_checkpoints_filters_by_namespace(self, isolated_repositories):
        """Test that list_checkpoints respects checkpoint_ns filter."""
        repo = isolated_repositories["checkpoint_repository"]

        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint={"id": "cp-1"},
            metadata={},
            blobs=[],
        )
        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="subgraph",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint={"id": "cp-1"},
            metadata={},
            blobs=[],
        )

        root_results = await repo.list_checkpoints(
            thread_id="thread-1", checkpoint_ns=""
        )
        sub_results = await repo.list_checkpoints(
            thread_id="thread-1", checkpoint_ns="subgraph"
        )

        assert len(root_results) == 1
        assert len(sub_results) == 1
        assert root_results[0]["checkpoint_ns"] == ""
        assert sub_results[0]["checkpoint_ns"] == "subgraph"

    # ── parent checkpoint tracking ──

    async def test_parent_checkpoint_id_tracked(self, isolated_repositories):
        """Test that parent_checkpoint_id is stored and returned correctly."""
        repo = isolated_repositories["checkpoint_repository"]

        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint={"id": "cp-1"},
            metadata={},
            blobs=[],
        )
        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-2",
            parent_checkpoint_id="cp-1",
            checkpoint={"id": "cp-2"},
            metadata={},
            blobs=[],
        )

        result = await repo.get_tuple(
            thread_id="thread-1", checkpoint_ns="", checkpoint_id="cp-2"
        )
        assert result is not None
        assert result["parent_checkpoint_id"] == "cp-1"

    # ── blob edge cases ──

    async def test_null_blob_stored_correctly(self, isolated_repositories):
        """Test that a blob with None data is stored and returned."""
        repo = isolated_repositories["checkpoint_repository"]

        blobs = [
            {"channel": "empty_channel", "version": "v1", "type": "empty", "blob": None},
        ]
        checkpoint = {
            "id": "cp-1",
            "channel_versions": {"empty_channel": "v1"},
        }

        await repo.put(
            thread_id="thread-1",
            checkpoint_ns="",
            checkpoint_id="cp-1",
            parent_checkpoint_id=None,
            checkpoint=checkpoint,
            metadata={},
            blobs=blobs,
        )

        result = await repo.get_tuple(
            thread_id="thread-1", checkpoint_ns="", checkpoint_id="cp-1"
        )
        assert result is not None
        assert len(result["blobs"]) == 1
        assert result["blobs"][0]["type"] == "empty"
        assert result["blobs"][0]["blob"] is None
