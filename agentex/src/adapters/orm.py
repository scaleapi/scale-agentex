from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy import (
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from src.domain.entities.agent_api_keys import AgentAPIKeyType
from src.domain.entities.agents import AgentInputType, AgentStatus
from src.domain.entities.tasks import TaskStatus
from src.utils.ids import orm_id

BaseORM = declarative_base()


class AgentORM(BaseORM):
    __tablename__ = "agents"
    id = Column(String, primary_key=True, default=orm_id)  # Using UUIDs for IDs
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    docker_image = Column(String, nullable=True)
    status = Column(SQLAlchemyEnum(AgentStatus), nullable=False)
    status_reason = Column(Text, nullable=True)
    acp_url = Column(String, nullable=True)  # URL of the agent's ACP server
    # TODO: make this a SQLAlchemyEnum rather than a string
    acp_type = Column(String, nullable=False, server_default="async")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    registration_metadata = Column(JSONB, nullable=True)
    registered_at = Column(DateTime(timezone=True), nullable=True)
    agent_input_type = Column(SQLAlchemyEnum(AgentInputType), nullable=True)

    # Many-to-Many relationship with tasks
    tasks = relationship("TaskORM", secondary="task_agents", back_populates="agents")

    # Indexes for efficient querying
    __table_args__ = (
        # Index for filtering agents by status (used in list queries)
        Index("ix_agents_status", "status"),
    )


class TaskORM(BaseORM):
    __tablename__ = "tasks"
    id = Column(String, primary_key=True, default=orm_id)  # Using UUIDs for IDs
    name = Column(
        String, unique=True, nullable=True, index=True
    )  # Temporarily allowing NULL values
    status = Column(SQLAlchemyEnum(TaskStatus), nullable=True)
    status_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    params = Column(JSONB, nullable=True)
    task_metadata = Column(JSONB, nullable=True)
    # Many-to-Many relationship with agents
    agents = relationship("AgentORM", secondary="task_agents", back_populates="tasks")

    # Indexes for efficient querying
    __table_args__ = (
        # Index for filtering tasks by status (used in list queries)
        Index("ix_tasks_status", "status"),
    )


class TaskAgentORM(BaseORM):
    __tablename__ = "task_agents"
    task_id = Column(String, ForeignKey("tasks.id"), primary_key=True)
    agent_id = Column(String, ForeignKey("agents.id"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EventORM(BaseORM):
    __tablename__ = "events"

    # UUID for external references and idempotency
    id = Column(String, nullable=False, default=orm_id, unique=True)

    # Primary key - auto-incrementing 64-bit integer for reliable ordering
    sequence_id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Foreign keys to tasks and agents
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False)

    # Event type and data
    content = Column(JSONB, nullable=True)

    # Timestamp - No updated at because it should be immutable
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Composite indexes for efficient querying
    __table_args__ = (
        # Index for querying events by agent, task, and order
        Index("idx_events_agent_task_order", "agent_id", "task_id", "sequence_id"),
        # Index for querying events by agent and order
        Index("idx_events_agent_order", "agent_id", "sequence_id"),
    )


class AgentTaskTrackerORM(BaseORM):
    __tablename__ = "agent_task_tracker"
    id = Column(String, primary_key=True, default=orm_id)
    agent_id = Column(String, ForeignKey("agents.id"), primary_key=True)
    task_id = Column(String, ForeignKey("tasks.id"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Leaving this as text on purpose to allow for more flexible statuses
    status = Column(Text, nullable=True)
    status_reason = Column(Text, nullable=True)
    last_processed_event_id = Column(String, nullable=True)

    # Indexes for efficient querying
    __table_args__ = (
        # Index for querying by agent_id and task_id
        Index(
            "idx_agent_task_tracker_agent_task",
            "agent_id",
            "task_id",
        ),
    )


class SpanORM(BaseORM):
    __tablename__ = "spans"
    id = Column(String, primary_key=True, default=orm_id)  # Using UUIDs for IDs
    trace_id = Column(String, nullable=False)
    parent_id = Column(String, nullable=True)
    name = Column(String, nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)
    input = Column(JSON, nullable=True)
    output = Column(JSON, nullable=True)
    data = Column(JSON, nullable=True)

    # Indexes for efficient querying
    __table_args__ = (
        # Index for filtering spans by trace_id
        Index("ix_spans_trace_id", "trace_id"),
        # Composite index for filtering by trace_id and ordering by start_time
        Index("ix_spans_trace_id_start_time", "trace_id", "start_time"),
        # Index for traversing span hierarchy
        Index("ix_spans_parent_id", "parent_id"),
    )


class AgentAPIKeyORM(BaseORM):
    __tablename__ = "agent_api_keys"
    id = Column(String, primary_key=True, default=orm_id)
    agent_id = Column(String(64), ForeignKey("agents.id"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    name = Column(String(256), nullable=False, index=True)
    api_key_type = Column(SQLAlchemyEnum(AgentAPIKeyType), nullable=False)
    api_key = Column(String, nullable=False)

    # Indexes for efficient querying
    __table_args__ = (
        # Index for querying by agent_id
        Index(
            "idx_agent_api_keys_agent",
            "agent_id",
        ),
        # Index for querying by api_key
        Index(
            "ix_agent_api_keys_api_key",
            "api_key",
        ),
    )


class DeploymentHistoryORM(BaseORM):
    __tablename__ = "deployment_history"

    id = Column(String, primary_key=True, default=orm_id)
    agent_id = Column(String(64), ForeignKey("agents.id"))

    # Deployment metadata
    author_name = Column(String, nullable=False)
    author_email = Column(String, nullable=False)
    branch_name = Column(String, nullable=False)
    build_timestamp = Column(DateTime(timezone=True), nullable=False)
    deployment_timestamp = Column(DateTime(timezone=True), nullable=False)
    commit_hash = Column(String, nullable=False)

    # Indexes for efficient querying
    __table_args__ = (
        # Index for querying by agent_id
        Index(
            "idx_deployment_history_agent",
            "agent_id",
        ),
        # Index for querying by commit_hash
        Index(
            "ix_deployment_history_commit_hash",
            "commit_hash",
        ),
    )
