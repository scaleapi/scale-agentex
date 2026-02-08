from enum import Enum
from typing import Any

from pydantic import Field, RootModel, model_validator

from src.api.schemas.events import Event
from src.api.schemas.json_rpc import JSONRPCRequest, JSONRPCResponse
from src.api.schemas.task_message_updates import TaskMessageUpdate
from src.api.schemas.task_messages import TaskMessage, TaskMessageContent
from src.api.schemas.tasks import Task
from src.utils.logging import make_logger
from src.utils.model_utils import BaseModel

logger = make_logger(__name__)


class AgentRPCMethod(str, Enum):
    EVENT_SEND = "event/send"
    TASK_CREATE = "task/create"
    MESSAGE_SEND = "message/send"
    TASK_CANCEL = "task/cancel"


class CreateTaskRequest(BaseModel):
    name: str | None = Field(None, description="The name of the task to create")
    params: dict[str, Any] | None = Field(
        None, description="The parameters for the task"
    )


class CancelTaskRequest(BaseModel):
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


class SendMessageRequest(BaseModel):
    task_id: str | None = Field(
        None, description="The ID of the task that the message was sent to"
    )
    task_name: str | None = Field(
        None, description="The name of the task that the message was sent to"
    )
    content: TaskMessageContent = Field(
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


class SendEventRequest(BaseModel):
    task_id: str | None = Field(
        None, description="The ID of the task that the event was sent to"
    )
    task_name: str | None = Field(
        None, description="The name of the task that the event was sent to"
    )
    content: TaskMessageContent | None = Field(
        None, description="The content to send to the event"
    )

    @model_validator(mode="after")
    def validate_task_identifiers(self):
        if self.task_id is not None and self.task_name is not None:
            raise ValueError("Cannot provide both task_id and task_name - use only one")
        return self


class AgentRPCParams(RootModel):
    root: (
        CreateTaskRequest | CancelTaskRequest | SendMessageRequest | SendEventRequest
    ) = Field(..., description="The parameters for the agent RPC request")


class AgentRPCRequest(JSONRPCRequest):
    method: AgentRPCMethod
    params: AgentRPCParams

    @model_validator(mode="before")
    @classmethod
    def validate_params_based_on_method(cls, data):
        """Validate and deserialize params based on the method field"""
        if isinstance(data, dict):
            method = data.get("method")
            params_data = data.get("params")

            if method and params_data:
                # Determine the correct params type based on method
                if method == AgentRPCMethod.TASK_CREATE:
                    data["params"] = AgentRPCParams(
                        root=CreateTaskRequest(**params_data)
                    )
                elif method == AgentRPCMethod.TASK_CANCEL:
                    data["params"] = AgentRPCParams(
                        root=CancelTaskRequest(**params_data)
                    )
                elif method == AgentRPCMethod.MESSAGE_SEND:
                    data["params"] = AgentRPCParams(
                        root=SendMessageRequest(**params_data)
                    )
                elif method == AgentRPCMethod.EVENT_SEND:
                    data["params"] = AgentRPCParams(
                        root=SendEventRequest(**params_data)
                    )
                else:
                    raise ValueError(f"Unknown method: {method}")

        return data


class AgentRPCResult(RootModel):
    root: list[TaskMessage] | TaskMessageUpdate | Task | Event | None


class AgentRPCResponse(JSONRPCResponse):
    result: AgentRPCResult = Field(
        default=..., description="The result of the agent RPC request"
    )
