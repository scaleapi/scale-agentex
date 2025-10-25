from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

from src.api.schemas.agents_rpc import (
    AgentRPCRequest,
    CancelTaskRequest,
    CreateTaskRequest,
)
from src.domain.entities.agents import ACPType, AgentEntity
from src.domain.entities.events import EventEntity
from src.domain.entities.json_rpc import JSONRPCRequest
from src.domain.entities.task_messages import (
    TaskMessageContentEntity,
    convert_task_message_content_to_entity,
)
from src.domain.entities.tasks import TaskEntity
from src.utils.logging import make_logger

logger = make_logger(__name__)


class AgentRPCMethod(str, Enum):
    """Available JSON-RPC methods for agent communication"""

    TASK_CREATE = "task/create"
    TASK_CANCEL = "task/cancel"
    MESSAGE_SEND = "message/send"
    EVENT_SEND = "event/send"


class CreateTaskParams(BaseModel):
    """Parameters for task/create method"""

    agent: AgentEntity = Field(
        ...,
        description="The agent that the created task has been sent to",
    )
    task: TaskEntity = Field(..., description="The task that was created")
    params: dict[str, Any] | None = Field(
        None,
        description="The parameters for the task as inputted by the user",
    )


class SendMessageParams(BaseModel):
    """Parameters for message/send method"""

    agent: AgentEntity = Field(
        ...,
        description="The agent that the message was sent to",
    )
    task: TaskEntity = Field(..., description="The task that the message was sent to")
    content: TaskMessageContentEntity = Field(
        ..., description="The message that was sent to the agent"
    )
    stream: bool = Field(
        False, description="Whether to stream the message to the agent"
    )


class SendEventParams(BaseModel):
    """Parameters for event/send method"""

    agent: AgentEntity = Field(
        ...,
        description="The agent that the event was sent to",
    )
    task: TaskEntity = Field(..., description="The task that the event was sent to")
    event: EventEntity = Field(..., description="The ID of the event")


class CancelTaskParams(BaseModel):
    """Parameters for task/cancel method"""

    agent: AgentEntity = Field(
        ...,
        description="The agent that the task was sent to",
    )
    task: TaskEntity = Field(..., description="The task that was cancelled")


ACP_TYPE_TO_ALLOWED_RPC_METHODS = {
    ACPType.SYNC: [AgentRPCMethod.MESSAGE_SEND, AgentRPCMethod.TASK_CREATE],
    ACPType.AGENTIC: [
        AgentRPCMethod.TASK_CREATE,
        AgentRPCMethod.TASK_CANCEL,
        AgentRPCMethod.EVENT_SEND,
    ],
}


class CreateTaskRequestEntity(BaseModel):
    name: str | None = Field(None, description="The name of the task to create")
    params: dict[str, Any] | None = Field(
        None, description="The parameters for the task"
    )


class CancelTaskRequestEntity(BaseModel):
    task_id: str | None = Field(
        None,
        description="The ID of the task to cancel. Either this or task_name must be provided.",
    )
    task_name: str | None = Field(
        None,
        description="The name of the task to cancel. Either this or task_id must be provided.",
    )

    @model_validator(mode="after")
    def validate_task_identifiers(self):
        if self.task_id is not None and self.task_name is not None:
            raise ValueError("Cannot provide both task_id and task_name - use only one")
        return self


class SendMessageRequestEntity(BaseModel):
    task_id: str | None = Field(
        None, description="The ID of the task that the message was sent to"
    )
    task_name: str | None = Field(
        None, description="The name of the task that the message was sent to"
    )
    content: TaskMessageContentEntity = Field(
        ..., description="The message that was sent to the agent"
    )
    stream: bool = Field(
        False, description="Whether to stream the response message back to the client"
    )
    task_params: dict[str, Any] | None = Field(
        None,
        description="The parameters for the task (only used when creating new tasks)",
    )

    @model_validator(mode="after")
    def validate_task_identifiers(self):
        if self.task_id is not None and self.task_name is not None:
            raise ValueError("Cannot provide both task_id and task_name - use only one")
        return self


class SendEventRequestEntity(BaseModel):
    task_id: str | None = Field(
        None, description="The ID of the task that the event was sent to"
    )
    task_name: str | None = Field(
        None, description="The name of the task that the event was sent to"
    )
    content: TaskMessageContentEntity | None = Field(
        None, description="The content to send to the event"
    )

    @model_validator(mode="after")
    def validate_task_identifiers(self):
        if self.task_id is not None and self.task_name is not None:
            raise ValueError("Cannot provide both task_id and task_name - use only one")
        return self


class AgentRPCRequestEntity(JSONRPCRequest):
    method: AgentRPCMethod
    params: (
        CreateTaskRequestEntity
        | CancelTaskRequestEntity
        | SendMessageRequestEntity
        | SendEventRequestEntity
    ) = Field(..., description="The parameters for the agent RPC request")

    @classmethod
    def from_api_request(cls, request: AgentRPCRequest) -> Self:
        if request.method == AgentRPCMethod.TASK_CREATE and isinstance(
            request.params.root, CreateTaskRequest
        ):
            params = CreateTaskRequestEntity(
                name=request.params.root.name,
                params=request.params.root.params,
            )
        elif request.method == AgentRPCMethod.TASK_CANCEL and isinstance(
            request.params.root, CancelTaskRequest
        ):
            params = CancelTaskRequestEntity(
                task_id=request.params.root.task_id,
                task_name=request.params.root.task_name,
            )
        elif request.method == AgentRPCMethod.MESSAGE_SEND:
            content_entity = convert_task_message_content_to_entity(
                content=request.params.root.content.root
            )
            params = SendMessageRequestEntity(
                task_id=request.params.root.task_id,
                task_name=request.params.root.task_name,
                content=content_entity,
                stream=request.params.root.stream,
                task_params=request.params.root.task_params,
            )
        elif request.method == AgentRPCMethod.EVENT_SEND:
            if request.params.root.content is not None:
                content_entity = convert_task_message_content_to_entity(
                    content=request.params.root.content.root
                )
            else:
                content_entity = None
            params = SendEventRequestEntity(
                task_id=request.params.root.task_id,
                task_name=request.params.root.task_name,
                content=content_entity,
            )
        else:
            logger.error(f"Invalid method from request: {request}")
            raise ValueError(f"Invalid method: {request.method}")

        return cls(
            method=AgentRPCMethod(request.method),
            params=params,
        )
