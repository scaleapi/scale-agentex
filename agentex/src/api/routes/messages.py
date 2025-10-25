from fastapi import APIRouter

from src.api.schemas.authorization_types import (
    AgentexResourceType,
    AuthorizedOperationType,
)
from src.api.schemas.task_messages import (
    BatchCreateTaskMessagesRequest,
    BatchUpdateTaskMessagesRequest,
    CreateTaskMessageRequest,
    TaskMessage,
    UpdateTaskMessageRequest,
)
from src.domain.entities.task_messages import convert_task_message_content_to_entity
from src.domain.use_cases.messages_use_case import DMessageUseCase
from src.utils.authorization_shortcuts import DAuthorizedBodyId, DAuthorizedQuery

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.post(
    "/batch",
    response_model=list[TaskMessage],
)
async def batch_create_messages(
    request: BatchCreateTaskMessagesRequest,
    message_use_case: DMessageUseCase,
    _authorized_task_id: DAuthorizedBodyId(
        AgentexResourceType.task, AuthorizedOperationType.execute
    ),
) -> list[TaskMessage]:
    # Convert each content from API schema to entity schema
    converted_contents = [
        convert_task_message_content_to_entity(content.root)
        for content in request.contents
    ]

    task_message_entities = await message_use_case.create_batch(
        task_id=request.task_id,
        contents=converted_contents,
    )
    return [
        TaskMessage.model_validate(task_message_entity)
        for task_message_entity in task_message_entities
    ]


@router.put(
    "/batch",
    response_model=list[TaskMessage],
)
async def batch_update_messages(
    request: BatchUpdateTaskMessagesRequest,
    message_use_case: DMessageUseCase,
    _authorized_task_id: DAuthorizedBodyId(
        AgentexResourceType.task, AuthorizedOperationType.execute
    ),
) -> list[TaskMessage]:
    task_message_entities = await message_use_case.update_batch(
        task_id=request.task_id,
        updates=request.updates,
    )
    return [
        TaskMessage.model_validate(task_message_entity)
        for task_message_entity in task_message_entities
    ]


@router.post(
    "",
    response_model=TaskMessage,
)
async def create_message(
    request: CreateTaskMessageRequest,
    message_use_case: DMessageUseCase,
    _authorized_task_id: DAuthorizedBodyId(
        AgentexResourceType.task, AuthorizedOperationType.execute
    ),
) -> TaskMessage:
    task_message_entity = await message_use_case.create(
        task_id=request.task_id,
        content=convert_task_message_content_to_entity(request.content.root),
        streaming_status=request.streaming_status,
    )
    return TaskMessage.model_validate(task_message_entity)


@router.put(
    "/{message_id}",
    response_model=TaskMessage,
)
async def update_message(
    request: UpdateTaskMessageRequest,
    message_id: str,
    message_use_case: DMessageUseCase,
    _authorized_task_id: DAuthorizedBodyId(
        AgentexResourceType.task, AuthorizedOperationType.execute
    ),
) -> TaskMessage:
    task_message_entity = await message_use_case.update(
        task_id=request.task_id,
        message_id=message_id,
        content=convert_task_message_content_to_entity(request.content.root),
        streaming_status=request.streaming_status,
    )
    return TaskMessage.model_validate(task_message_entity)


@router.get(
    "",
    response_model=list[TaskMessage],
)
async def list_messages(
    task_id: DAuthorizedQuery(AgentexResourceType.task, AuthorizedOperationType.read),
    message_use_case: DMessageUseCase,
    limit: int = 50,
    page_number: int = 1,
) -> list[TaskMessage]:
    task_message_entities = await message_use_case.list_messages(
        task_id=task_id, limit=limit, page_number=page_number
    )

    return [
        TaskMessage.model_validate(task_message_entity)
        for task_message_entity in task_message_entities
    ]


@router.get(
    "/{message_id}",
    response_model=TaskMessage,
)
async def get_message(
    message_id: str,
    message_use_case: DMessageUseCase,
) -> TaskMessage | None:
    task_message_entity = await message_use_case.get_message(
        message_id=message_id,
    )
    return (
        TaskMessage.model_validate(task_message_entity) if task_message_entity else None
    )
