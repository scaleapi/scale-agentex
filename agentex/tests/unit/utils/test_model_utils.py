"""
Unit tests for model_utils.py SQLAlchemy relationship extraction.

Tests the BaseModel class's ability to extract both column values and
loaded relationships from SQLAlchemy ORM objects.
"""

import os
import sys
from datetime import UTC, datetime

import pytest
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    create_engine,
    func,
    select,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship, selectinload

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from domain.entities.agents import AgentEntity, AgentStatus
from domain.entities.tasks import TaskEntity, TaskStatus
from utils.ids import orm_id

# Create test-specific ORM models that use JSON instead of JSONB for SQLite compatibility
TestBaseORM = declarative_base()


class TestAgentORM(TestBaseORM):
    """Test version of AgentORM using JSON instead of JSONB for SQLite"""

    __tablename__ = "test_agents"
    id = Column(String, primary_key=True, default=orm_id)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    docker_image = Column(String, nullable=True)
    status = Column(SQLAlchemyEnum(AgentStatus), nullable=False)
    status_reason = Column(Text, nullable=True)
    acp_url = Column(String, nullable=True)
    acp_type = Column(String, nullable=False, server_default="agentic")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    registration_metadata = Column(JSON, nullable=True)  # JSON instead of JSONB
    registered_at = Column(DateTime(timezone=True), nullable=True)

    tasks = relationship(
        "TestTaskORM", secondary="test_task_agents", back_populates="agents"
    )


class TestTaskORM(TestBaseORM):
    """Test version of TaskORM using JSON instead of JSONB for SQLite"""

    __tablename__ = "test_tasks"
    id = Column(String, primary_key=True, default=orm_id)
    name = Column(String, unique=True, nullable=True, index=True)
    status = Column(SQLAlchemyEnum(TaskStatus), nullable=True)
    status_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    params = Column(JSON, nullable=True)  # JSON instead of JSONB
    task_metadata = Column(JSON, nullable=True)  # JSON instead of JSONB

    agents = relationship(
        "TestAgentORM", secondary="test_task_agents", back_populates="tasks"
    )


class TestTaskAgentORM(TestBaseORM):
    """Test version of TaskAgentORM"""

    __tablename__ = "test_task_agents"
    task_id = Column(String, ForeignKey("test_tasks.id"), primary_key=True)
    agent_id = Column(String, ForeignKey("test_agents.id"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    TestBaseORM.metadata.create_all(engine)
    return engine


@pytest.mark.unit
def test_extract_columns_from_orm_object(in_memory_db):
    """Test that column values are correctly extracted from SQLAlchemy ORM objects"""
    with Session(in_memory_db) as session:
        # Create a task without relationships
        task_orm = TestTaskORM(
            id=orm_id(),
            name="test-task",
            status=TaskStatus.RUNNING,
            status_reason="Test reason",
            params={"key": "value"},
            task_metadata={"meta": "data"},
        )
        session.add(task_orm)
        session.commit()
        session.refresh(task_orm)

        # Convert to Pydantic entity
        task_entity = TaskEntity.model_validate(task_orm)

        # Verify all columns were extracted
        assert task_entity.id == task_orm.id
        assert task_entity.name == "test-task"
        assert task_entity.status == TaskStatus.RUNNING
        assert task_entity.status_reason == "Test reason"
        assert task_entity.params == {"key": "value"}
        assert task_entity.task_metadata == {"meta": "data"}
        assert task_entity.created_at is not None
        assert task_entity.updated_at is not None


@pytest.mark.unit
def test_extract_loaded_relationships(in_memory_db):
    """Test that loaded relationships are extracted from ORM objects"""
    with Session(in_memory_db) as session:
        # Create agent and task with relationship
        agent_orm = TestAgentORM(
            id=orm_id(),
            name="test-agent",
            description="Test agent description",
            status=AgentStatus.READY,
            acp_type="agentic",
        )
        task_orm = TestTaskORM(
            id=orm_id(),
            name="test-task",
            status=TaskStatus.RUNNING,
        )
        task_agent = TestTaskAgentORM(
            task_id=task_orm.id,
            agent_id=agent_orm.id,
        )

        session.add(agent_orm)
        session.add(task_orm)
        session.add(task_agent)
        session.commit()

        # Load task WITH agents relationship eagerly loaded
        stmt = (
            select(TestTaskORM)
            .where(TestTaskORM.id == task_orm.id)
            .options(selectinload(TestTaskORM.agents))
        )
        loaded_task = session.execute(stmt).scalar_one()

        # Convert to Pydantic entity
        task_entity = TaskEntity.model_validate(loaded_task)

        # Verify relationship was extracted
        assert hasattr(task_entity, "agents")
        assert task_entity.agents is not None
        assert len(task_entity.agents) == 1

        # Verify the agent data is accessible
        agent = task_entity.agents[0]
        assert isinstance(agent, TestAgentORM)
        assert agent.name == "test-agent"


@pytest.mark.unit
def test_unloaded_relationships_not_extracted(in_memory_db):
    """Test that unloaded relationships are NOT extracted (lazy loading)"""
    with Session(in_memory_db) as session:
        # Create agent and task with relationship
        agent_orm = TestAgentORM(
            id=orm_id(),
            name="test-agent",
            description="Test agent description",
            status=AgentStatus.READY,
            acp_type="agentic",
        )
        task_orm = TestTaskORM(
            id=orm_id(),
            name="test-task",
            status=TaskStatus.RUNNING,
        )
        task_agent = TestTaskAgentORM(
            task_id=task_orm.id,
            agent_id=agent_orm.id,
        )

        session.add(agent_orm)
        session.add(task_orm)
        session.add(task_agent)
        session.commit()

        # Load task WITHOUT eagerly loading agents relationship
        stmt = select(TestTaskORM).where(TestTaskORM.id == task_orm.id)
        loaded_task = session.execute(stmt).scalar_one()

        # Convert to Pydantic entity
        task_entity = TaskEntity.model_validate(loaded_task)

        # Verify relationship was NOT extracted (unloaded)
        # The validator should skip unloaded relationships
        assert not hasattr(task_entity, "agents") or task_entity.agents is None


@pytest.mark.unit
def test_non_orm_object_passthrough():
    """Test that non-ORM objects are passed through unchanged"""
    # Create a regular dict
    task_dict = {
        "id": orm_id(),
        "name": "test-task",
        "status": TaskStatus.RUNNING,
        "status_reason": "Test",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }

    # Convert to Pydantic entity
    task_entity = TaskEntity.model_validate(task_dict)

    # Verify it worked
    assert task_entity.id == task_dict["id"]
    assert task_entity.name == "test-task"
    assert task_entity.status == TaskStatus.RUNNING


@pytest.mark.unit
def test_base_model_from_dict():
    """Test BaseModel.from_dict() helper method"""
    task_dict = {
        "id": orm_id(),
        "name": "test-task",
        "status": TaskStatus.RUNNING,
    }

    task_entity = TaskEntity.from_dict(task_dict)

    assert task_entity is not None
    assert task_entity.id == task_dict["id"]
    assert task_entity.name == "test-task"

    # Test with None
    assert TaskEntity.from_dict(None) is None


@pytest.mark.unit
def test_base_model_from_json():
    """Test BaseModel.from_json() helper method"""
    json_str = '{"id": "test-123", "name": "test-task", "status": "RUNNING"}'

    task_entity = TaskEntity.from_json(json_str)

    assert task_entity is not None
    assert task_entity.id == "test-123"
    assert task_entity.name == "test-task"
    assert task_entity.status == TaskStatus.RUNNING

    # Test with None
    assert TaskEntity.from_json(None) is None


@pytest.mark.unit
def test_base_model_to_json():
    """Test BaseModel.to_json() method"""
    task_entity = TaskEntity(
        id="test-123",
        name="test-task",
        status=TaskStatus.RUNNING,
    )

    json_str = task_entity.to_json()

    assert "test-123" in json_str
    assert "test-task" in json_str
    assert "RUNNING" in json_str


@pytest.mark.unit
def test_base_model_to_dict():
    """Test BaseModel.to_dict() method"""
    task_entity = TaskEntity(
        id="test-123",
        name="test-task",
        status=TaskStatus.RUNNING,
    )

    task_dict = task_entity.to_dict()

    assert task_dict["id"] == "test-123"
    assert task_dict["name"] == "test-task"
    assert task_dict["status"] == "RUNNING"  # Enum converted to string


@pytest.mark.unit
def test_base_model_from_model():
    """Test BaseModel.from_model() helper method"""
    original = TaskEntity(
        id="test-123",
        name="test-task",
        status=TaskStatus.RUNNING,
    )

    # Create a new instance from the original
    copied = TaskEntity.from_model(original)

    assert copied is not None
    assert copied.id == original.id
    assert copied.name == original.name
    assert copied.status == original.status

    # Test with None
    assert TaskEntity.from_model(None) is None


@pytest.mark.unit
def test_many_to_many_relationship_extraction(in_memory_db):
    """Test extraction of many-to-many relationships (task with multiple agents)"""
    with Session(in_memory_db) as session:
        # Create multiple agents
        agent1 = TestAgentORM(
            id=orm_id(),
            name="agent-1",
            description="First agent",
            status=AgentStatus.READY,
            acp_type="agentic",
        )
        agent2 = TestAgentORM(
            id=orm_id(),
            name="agent-2",
            description="Second agent",
            status=AgentStatus.READY,
            acp_type="agentic",
        )

        task_orm = TestTaskORM(
            id=orm_id(),
            name="multi-agent-task",
            status=TaskStatus.RUNNING,
        )

        # Create relationships
        task_agent1 = TestTaskAgentORM(task_id=task_orm.id, agent_id=agent1.id)
        task_agent2 = TestTaskAgentORM(task_id=task_orm.id, agent_id=agent2.id)

        session.add_all([agent1, agent2, task_orm, task_agent1, task_agent2])
        session.commit()

        # Load task with eagerly loaded agents
        stmt = (
            select(TestTaskORM)
            .where(TestTaskORM.id == task_orm.id)
            .options(selectinload(TestTaskORM.agents))
        )
        loaded_task = session.execute(stmt).scalar_one()

        # Convert to Pydantic entity
        task_entity = TaskEntity.model_validate(loaded_task)

        # Verify both agents were extracted
        assert hasattr(task_entity, "agents")
        assert len(task_entity.agents) == 2
        agent_names = {agent.name for agent in task_entity.agents}
        assert agent_names == {"agent-1", "agent-2"}


@pytest.mark.unit
def test_agent_entity_with_task_relationships(in_memory_db):
    """
    Test that AgentEntity conversion succeeds even when relationships are loaded.

    Note: AgentEntity doesn't have extra='allow' configuration, so loaded relationships
    are extracted by the validator but then ignored during model construction. This is
    expected behavior - only entities with extra='allow' will include relationships.
    """
    with Session(in_memory_db) as session:
        # Create agent with multiple tasks
        agent_orm = TestAgentORM(
            id=orm_id(),
            name="test-agent",
            description="Test agent",
            status=AgentStatus.READY,
            acp_type="agentic",
        )

        task1 = TestTaskORM(id=orm_id(), name="task-1", status=TaskStatus.RUNNING)
        task2 = TestTaskORM(id=orm_id(), name="task-2", status=TaskStatus.COMPLETED)

        task_agent1 = TestTaskAgentORM(task_id=task1.id, agent_id=agent_orm.id)
        task_agent2 = TestTaskAgentORM(task_id=task2.id, agent_id=agent_orm.id)

        session.add_all([agent_orm, task1, task2, task_agent1, task_agent2])
        session.commit()

        # Load agent with eagerly loaded tasks
        stmt = (
            select(TestAgentORM)
            .where(TestAgentORM.id == agent_orm.id)
            .options(selectinload(TestAgentORM.tasks))
        )
        loaded_agent = session.execute(stmt).scalar_one()

        # Convert to Pydantic entity - should succeed without error
        agent_entity = AgentEntity.model_validate(loaded_agent)

        # Verify core fields were extracted correctly
        assert agent_entity.id == agent_orm.id
        assert agent_entity.name == "test-agent"
        assert agent_entity.status == AgentStatus.READY

        # Tasks relationship is NOT included because AgentEntity doesn't have extra='allow'
        # This is expected behavior
        assert not hasattr(agent_entity, "tasks")
