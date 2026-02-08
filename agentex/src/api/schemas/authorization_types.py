from enum import StrEnum

from src.utils.model_utils import BaseModel


class AuthorizedOperationType(StrEnum):
    create = "create"
    read = "read"
    update = "update"
    delete = "delete"
    execute = "execute"


class AgentexResourceType(StrEnum):
    agent = "agent"
    task = "task"


# Resources that inherit permissions from their parent task
class TaskChildResourceType(StrEnum):
    """Resources that inherit permissions from their parent task."""

    event = "event"
    state = "state"


class AgentexResource(BaseModel):
    type: AgentexResourceType
    selector: str

    # Convenience constructors for easier instantiation from code, e.g. AgentexResource.agent("123")
    @classmethod
    def agent(cls, selector: str) -> "AgentexResource":
        return cls(type=AgentexResourceType.agent, selector=selector)

    @classmethod
    def task(cls, selector: str) -> "AgentexResource":
        return cls(type=AgentexResourceType.task, selector=selector)


class AgentexResourceOptionalSelector(BaseModel):
    type: AgentexResourceType
    selector: str | None = None

    @classmethod
    def agent(cls, selector: str | None = None) -> "AgentexResourceOptionalSelector":
        return cls(type=AgentexResourceType.agent, selector=selector)

    @classmethod
    def task(cls, selector: str | None = None) -> "AgentexResourceOptionalSelector":
        return cls(type=AgentexResourceType.task, selector=selector)
