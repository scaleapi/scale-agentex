import asyncio

import pytest
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.entities.tasks import TaskEntity, TaskStatus
from src.domain.use_cases.streams_use_case import StreamsUseCase
from src.domain.use_cases.tasks_use_case import TasksUseCase
from src.utils.ids import orm_id


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskEventStream:
    """Integration tests for the task event stream"""

    @pytest.fixture
    async def test_agent_and_task(self, isolated_repositories):
        """Create a test agent and task for streaming tests"""
        agent_repo = isolated_repositories["agent_repository"]
        task_repo = isolated_repositories["task_repository"]

        # Create test agent
        agent_id = orm_id()
        agent = AgentEntity(
            id=agent_id,
            name=agent_id,
            description="Agent for stream testing",
            docker_image="test/stream:latest",
            status=AgentStatus.READY,
            acp_url="http://stream-test:8000/acp",
            acp_type=ACPType.SYNC,
        )
        created_agent = await agent_repo.create(agent)

        # Create test task with initial metadata
        initial_metadata = {
            "version": "1.0.0",
            "status": "initial",
            "stream_test": {
                "created_for": "integration_testing",
                "expected_events": ["task_updated"],
            },
        }

        task_id = orm_id()
        task = TaskEntity(
            id=task_id,
            name=task_id,
            status=TaskStatus.RUNNING,
            status_reason="Task created for stream integration testing",
            task_metadata=initial_metadata,
        )
        created_task = await task_repo.create(agent_id=created_agent.id, task=task)

        return created_agent, created_task

    @pytest.fixture
    def tasks_use_case(self, isolated_repositories):
        """Create TasksUseCase with real AgentTaskService like integration_client"""
        from src.domain.services.task_service import AgentTaskService

        # Mock ACP service to avoid external dependencies
        class MockAgentACPService:
            async def cancel_task(self, *args, **kwargs):
                pass

            async def send_event(self, *args, **kwargs):
                pass

            async def send_message(self, *args, **kwargs):
                pass

        task_service = AgentTaskService(
            acp_client=MockAgentACPService(),
            task_state_repository=isolated_repositories["task_state_repository"],
            task_repository=isolated_repositories["task_repository"],
            event_repository=isolated_repositories["event_repository"],
            stream_repository=isolated_repositories["redis_stream_repository"],
        )

        return TasksUseCase(task_service=task_service)

    @pytest.fixture
    def streams_use_case(self, isolated_repositories):
        """Create StreamsUseCase with isolated repositories"""
        from src.config.environment_variables import EnvironmentVariables
        from src.domain.services.task_service import AgentTaskService

        # Mock ACP service to avoid external dependencies
        class MockAgentACPService:
            async def cancel_task(self, *args, **kwargs):
                pass

            async def send_event(self, *args, **kwargs):
                pass

            async def send_message(self, *args, **kwargs):
                pass

        task_service = AgentTaskService(
            acp_client=MockAgentACPService(),
            task_state_repository=isolated_repositories["task_state_repository"],
            task_repository=isolated_repositories["task_repository"],
            event_repository=isolated_repositories["event_repository"],
            stream_repository=isolated_repositories["redis_stream_repository"],
        )

        environment_variables = EnvironmentVariables.refresh()

        return StreamsUseCase(
            stream_repository=isolated_repositories["redis_stream_repository"],
            task_service=task_service,
            environment_variables=environment_variables,
        )

    async def test_update_mutable_fields_on_task_triggers_stream_event(
        self, test_agent_and_task, tasks_use_case, streams_use_case
    ):
        """Test that updating task metadata via TasksUseCase triggers a stream event"""
        # Given
        _agent, task = test_agent_and_task

        # Updated metadata to apply
        updated_metadata = {
            "version": "2.0.0",
            "status": "updated_via_use_case",
            "stream_test": {
                "created_for": "integration_testing",
                "expected_events": ["task_updated"],
                "updated_at": "2024-01-01T12:00:00Z",
            },
            "integration_test": {
                "test_type": "stream_event",
                "verification": "metadata_update_triggers_event",
                "data_types": {
                    "string": "test_value",
                    "number": 42,
                    "float": 3.14,
                    "boolean": True,
                    "null_value": None,
                    "array": [1, 2, 3],
                    "nested": {"deep": "value"},
                },
            },
        }

        # Start streaming in the background
        stream_events = []
        stream_task = None

        async def collect_stream_events():
            """Collect events from the stream"""
            try:
                async for event_data in streams_use_case.stream_task_events(
                    task_id=task.id
                ):
                    # Parse the SSE data format
                    if event_data.startswith("data: "):
                        import json

                        event_json = event_data[6:].strip()  # Remove "data: " prefix
                        if event_json:  # Skip empty lines
                            try:
                                event = json.loads(event_json)
                                stream_events.append(event)
                                # Stop after receiving the task_updated event
                                if event.get("type") == "task_updated":
                                    break
                            except json.JSONDecodeError:
                                pass  # Skip malformed JSON
            except asyncio.CancelledError:
                pass  # Expected when we cancel the stream

        # When - Start the stream and update the metadata
        stream_task = asyncio.create_task(collect_stream_events())

        # Give the stream a moment to initialize
        await asyncio.sleep(0.1)

        # Update task metadata via TasksUseCase
        updated_task = await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, task_metadata=updated_metadata
        )

        # Give the stream time to process the event
        await asyncio.sleep(0.5)

        # Cancel the stream
        if stream_task:
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass

        # Then - Verify the stream event was received
        assert (
            len(stream_events) >= 1
        ), f"Expected at least 1 stream event, got {len(stream_events)}"

        # Find the task_updated event
        task_updated_events = [
            e for e in stream_events if e.get("type") == "task_updated"
        ]
        assert (
            len(task_updated_events) >= 1
        ), f"Expected task_updated event, got events: {[e.get('type') for e in stream_events]}"

        task_updated_event = task_updated_events[0]

        # Verify the event contains the updated task with new metadata
        assert "task" in task_updated_event
        event_task = task_updated_event["task"]
        assert event_task["id"] == task.id
        assert event_task["task_metadata"] == updated_metadata
        assert event_task["task_metadata"]["version"] == "2.0.0"
        assert event_task["task_metadata"]["status"] == "updated_via_use_case"
        assert (
            event_task["task_metadata"]["integration_test"]["verification"]
            == "metadata_update_triggers_event"
        )

        # Verify the TasksUseCase returned the updated task
        assert updated_task.id == task.id
        assert updated_task.task_metadata == updated_metadata

        print("✅ Task metadata update successfully triggered stream event")

    async def test_get_task_returns_updated_metadata_after_stream_update(
        self, test_agent_and_task, tasks_use_case
    ):
        """Test that TasksUseCase.get_task returns the updated metadata after update"""
        # Given
        _agent, task = test_agent_and_task

        # Verify initial state
        initial_task = await tasks_use_case.get_task(id=task.id)
        assert initial_task.task_metadata["version"] == "1.0.0"
        assert initial_task.task_metadata["status"] == "initial"

        # Updated metadata
        updated_metadata = {
            "version": "3.0.0",
            "status": "updated_and_verified",
            "stream_test": {
                "created_for": "integration_testing",
                "expected_events": ["task_updated"],
                "verification_step": "get_task_after_update",
            },
            "persistence_test": {
                "updated_via": "tasks_use_case",
                "expected_retrieval": "same_data",
                "complex_data": {
                    "nested_levels": {
                        "level1": {
                            "level2": {
                                "level3": "deep_value",
                                "array_data": ["item1", "item2", "item3"],
                                "numeric_data": 123.456,
                                "boolean_data": True,
                            }
                        }
                    }
                },
            },
        }

        # When - Update metadata and then retrieve the task
        await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, task_metadata=updated_metadata
        )
        retrieved_task = await tasks_use_case.get_task(id=task.id)

        # Then - Verify retrieved task has the updated metadata
        assert retrieved_task.id == task.id
        assert retrieved_task.name == task.name
        assert retrieved_task.task_metadata == updated_metadata
        assert retrieved_task.task_metadata["version"] == "3.0.0"
        assert retrieved_task.task_metadata["status"] == "updated_and_verified"
        assert (
            retrieved_task.task_metadata["persistence_test"]["updated_via"]
            == "tasks_use_case"
        )

        # Verify deep nested data is preserved
        deep_value = retrieved_task.task_metadata["persistence_test"]["complex_data"][
            "nested_levels"
        ]["level1"]["level2"]["level3"]
        assert deep_value == "deep_value"

        array_data = retrieved_task.task_metadata["persistence_test"]["complex_data"][
            "nested_levels"
        ]["level1"]["level2"]["array_data"]
        assert array_data == ["item1", "item2", "item3"]

        numeric_data = retrieved_task.task_metadata["persistence_test"]["complex_data"][
            "nested_levels"
        ]["level1"]["level2"]["numeric_data"]
        assert numeric_data == 123.456

        print("✅ TasksUseCase.get_task returns updated metadata correctly")

    async def test_multiple_metadata_updates_generate_multiple_stream_events(
        self, test_agent_and_task, tasks_use_case, streams_use_case
    ):
        """Test that multiple metadata updates generate multiple stream events"""
        # Given
        _agent, task = test_agent_and_task

        # Collect stream events
        stream_events = []
        stream_task = None

        async def collect_stream_events():
            """Collect multiple events from the stream"""
            try:
                async for event_data in streams_use_case.stream_task_events(
                    task_id=task.id
                ):
                    if event_data.startswith("data: "):
                        import json

                        event_json = event_data[6:].strip()
                        if event_json:
                            try:
                                event = json.loads(event_json)
                                stream_events.append(event)
                                # Stop after receiving 3 task_updated events
                                task_updated_count = len(
                                    [
                                        e
                                        for e in stream_events
                                        if e.get("type") == "task_updated"
                                    ]
                                )
                                if task_updated_count >= 3:
                                    break
                            except json.JSONDecodeError:
                                pass
            except asyncio.CancelledError:
                pass

        # When - Start stream and perform multiple updates
        stream_task = asyncio.create_task(collect_stream_events())
        await asyncio.sleep(0.1)  # Let stream initialize

        # First update
        metadata_v1 = {
            "version": "1.1.0",
            "update_sequence": 1,
            "test_data": {"first_update": True},
        }
        await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, task_metadata=metadata_v1
        )
        await asyncio.sleep(0.2)  # Let event propagate

        # Second update
        metadata_v2 = {
            "version": "1.2.0",
            "update_sequence": 2,
            "test_data": {"second_update": True},
        }
        await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, task_metadata=metadata_v2
        )
        await asyncio.sleep(0.2)  # Let event propagate

        # Third update
        metadata_v3 = {
            "version": "1.3.0",
            "update_sequence": 3,
            "test_data": {"third_update": True},
        }
        await tasks_use_case.update_mutable_fields_on_task(
            id=task.id, task_metadata=metadata_v3
        )
        await asyncio.sleep(0.2)  # Let event propagate

        # Stop the stream
        if stream_task:
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass

        # Then - Verify we received multiple task_updated events
        task_updated_events = [
            e for e in stream_events if e.get("type") == "task_updated"
        ]
        assert (
            len(task_updated_events) >= 3
        ), f"Expected at least 3 task_updated events, got {len(task_updated_events)}"

        # Verify each event has the correct metadata for its update
        versions = [
            event["task"]["task_metadata"]["version"] for event in task_updated_events
        ]
        sequences = [
            event["task"]["task_metadata"]["update_sequence"]
            for event in task_updated_events
        ]

        assert "1.1.0" in versions
        assert "1.2.0" in versions
        assert "1.3.0" in versions
        assert 1 in sequences
        assert 2 in sequences
        assert 3 in sequences

        # Verify final state via get_task
        final_task = await tasks_use_case.get_task(id=task.id)
        assert final_task.task_metadata["version"] == "1.3.0"
        assert final_task.task_metadata["update_sequence"] == 3
        assert final_task.task_metadata["test_data"]["third_update"] is True

        print("✅ Multiple metadata updates generated multiple stream events")

    async def test_stream_connected_event_includes_task_id(
        self, test_agent_and_task, streams_use_case
    ):
        """Test that stream connection includes the correct task ID"""
        # Given
        _agent, task = test_agent_and_task

        # When - Start stream and capture the first event (should be connected event)
        stream_events = []

        async def collect_initial_event():
            async for event_data in streams_use_case.stream_task_events(
                task_id=task.id
            ):
                if event_data.startswith("data: "):
                    import json

                    event_json = event_data[6:].strip()
                    if event_json:
                        try:
                            event = json.loads(event_json)
                            stream_events.append(event)
                            # Stop after first event
                            break
                        except json.JSONDecodeError:
                            pass

        # Collect the connected event
        stream_task = asyncio.create_task(collect_initial_event())
        await asyncio.sleep(0.1)
        stream_task.cancel()
        try:
            await stream_task
        except asyncio.CancelledError:
            pass

        # Then - Verify the connected event has correct task ID
        assert len(stream_events) >= 1, "Expected at least 1 stream event (connected)"

        connected_event = stream_events[0]
        assert connected_event.get("type") == "connected"
        assert connected_event.get("taskId") == task.id

        print("✅ Stream connected event includes correct task ID")

    async def test_stream_sends_keepalive_pings_during_idle_periods(
        self, test_agent_and_task, streams_use_case
    ):
        """Test that stream sends keepalive pings when no messages arrive for 15+ seconds"""
        # Given
        _agent, task = test_agent_and_task

        # When - Start stream and wait for pings without sending any messages
        stream_events = []
        ping_count = 0

        async def collect_stream_data():
            nonlocal ping_count
            async for event_data in streams_use_case.stream_task_events(
                task_id=task.id
            ):
                if event_data.startswith("data: "):
                    # Count data events
                    stream_events.append("data")
                elif event_data.startswith(":ping"):
                    # Count ping events
                    ping_count += 1
                    # Stop after receiving 2 pings to verify pattern
                    if ping_count >= 2:
                        break

        # Collect events for up to 35 seconds (should see at least 2 pings at 15s intervals)
        stream_task = asyncio.create_task(collect_stream_data())

        try:
            # Wait up to 35 seconds for 2 pings
            await asyncio.wait_for(stream_task, timeout=35)
        except TimeoutError:
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass

        # Then - Verify we received at least 2 pings
        assert (
            ping_count >= 2
        ), f"Expected at least 2 ping messages during idle period, got {ping_count}"

        print(f"✅ Stream sent {ping_count} keepalive pings during idle period")
