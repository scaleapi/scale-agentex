import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

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
from src.domain.entities.task_messages import (
    TaskMessageEntityFilter,
    convert_task_message_content_to_entity,
)
from src.domain.use_cases.messages_use_case import DMessageUseCase
from src.utils.authorization_shortcuts import DAuthorizedBodyId, DAuthorizedQuery
from src.utils.model_utils import BaseModel
from src.utils.pagination import decode_cursor, encode_cursor

router = APIRouter(prefix="/messages", tags=["Messages"])

# Generate JSON schema reference for TaskMessageEntityFilter
_filter_schema = TaskMessageEntityFilter.model_json_schema()

FILTERS_DESCRIPTION = f"""JSON-encoded array of TaskMessageEntityFilter objects.

Schema: {json.dumps(_filter_schema, indent=2)}

Each filter can include:
- `content`: Filter by message content (type, author, data fields)
- `streaming_status`: Filter by status ("IN_PROGRESS" or "DONE")
- `exclude`: If true, excludes matching messages (default: false)

Multiple filters are combined: inclusionary filters (exclude=false) are OR'd together,
exclusionary filters (exclude=true) are OR'd and negated, then both groups are AND'd.
"""

FILTERS_EXAMPLES = {
    "single_filter": {
        "summary": "Filter by content type",
        "value": '{"content": {"type": "text"}}',
    },
    "multiple_types": {
        "summary": "Filter multiple content types (OR)",
        "value": '[{"content": {"type": "text"}}, {"content": {"type": "data"}}]',
    },
    "with_exclusion": {
        "summary": "Include data messages, exclude specific data types",
        "value": '[{"content": {"type": "data"}}, {"content": {"data": {"type": "error_report"}}, "exclude": true}]',
    },
    "nested_data": {
        "summary": "Filter by nested data field",
        "value": '{"content": {"data": {"type": "report_status_update"}}}',
    },
}


class PaginatedMessagesResponse(BaseModel):
    """Response with cursor pagination metadata."""

    data: list[TaskMessage] = Field(..., description="List of messages")
    next_cursor: str | None = Field(
        None, description="Cursor for fetching the next page of older messages"
    )
    has_more: bool = Field(
        False, description="Whether there are more messages to fetch"
    )


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
    order_by: str | None = None,
    order_direction: str = "desc",
    filters: str | None = Query(
        None, description=FILTERS_DESCRIPTION, openapi_examples=FILTERS_EXAMPLES
    ),
) -> list[TaskMessage]:
    """
    List messages for a task with offset-based pagination.

    For cursor-based pagination with infinite scroll support, use /messages/paginated.
    """
    # Parse the JSON filter string into a list of TaskMessageEntityFilter
    parsed_filters: list[TaskMessageEntityFilter] | None = None
    if filters:
        try:
            filters_data = json.loads(filters)
            # Support both single filter object and array of filters
            if isinstance(filters_data, list):
                parsed_filters = [TaskMessageEntityFilter(**f) for f in filters_data]
            else:
                parsed_filters = [TaskMessageEntityFilter(**filters_data)]
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON in filters parameter: {e.msg}",
            ) from e

    task_message_entities = await message_use_case.list_messages(
        task_id=task_id,
        limit=limit,
        page_number=page_number,
        order_by=order_by,
        order_direction=order_direction,
        filters=parsed_filters,
    )

    return [
        TaskMessage.model_validate(task_message_entity)
        for task_message_entity in task_message_entities
    ]


@router.get(
    "/paginated",
    response_model=PaginatedMessagesResponse,
)
async def list_messages_paginated(
    task_id: DAuthorizedQuery(AgentexResourceType.task, AuthorizedOperationType.read),
    message_use_case: DMessageUseCase,
    limit: int = 50,
    cursor: str | None = None,
    direction: Literal["older", "newer"] = "older",
    filters: str | None = Query(
        None, description=FILTERS_DESCRIPTION, openapi_examples=FILTERS_EXAMPLES
    ),
) -> PaginatedMessagesResponse:
    """
    List messages for a task with cursor-based pagination.

    This endpoint is designed for infinite scroll UIs where new messages may arrive
    while paginating through older ones.

    Args:
        task_id: The task ID to filter messages by
        limit: Maximum number of messages to return (default: 50)
        cursor: Opaque cursor string for pagination. Pass the `next_cursor` from
                a previous response to get the next page.
        direction: Pagination direction - "older" to get older messages (default),
                   "newer" to get newer messages.

    Returns:
        PaginatedMessagesResponse with:
        - data: List of messages (newest first when direction="older")
        - next_cursor: Cursor for fetching the next page (null if no more pages)
        - has_more: Whether there are more messages to fetch

    Example:
        First request: GET /messages/paginated?task_id=xxx&limit=50
        Next page: GET /messages/paginated?task_id=xxx&limit=50&cursor=<next_cursor>
    """
    # Parse the JSON filter string into a list of TaskMessageEntityFilter
    parsed_filters: list[TaskMessageEntityFilter] | None = None
    if filters:
        try:
            filters_data = json.loads(filters)
            # Support both single filter object and array of filters
            if isinstance(filters_data, list):
                parsed_filters = [TaskMessageEntityFilter(**f) for f in filters_data]
            else:
                parsed_filters = [TaskMessageEntityFilter(**filters_data)]
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON in filters parameter: {e.msg}",
            ) from e

    # Decode cursor if provided
    before_id = None
    after_id = None
    if cursor:
        try:
            cursor_data = decode_cursor(cursor)
            if direction == "older":
                before_id = cursor_data.id
            else:
                after_id = cursor_data.id
        except ValueError:
            # Invalid cursor, ignore and return from start
            pass

    # Fetch one extra to determine if there are more results
    task_message_entities = await message_use_case.list_messages(
        task_id=task_id,
        limit=limit + 1,
        page_number=1,
        order_by=None,
        order_direction="desc",
        before_id=before_id,
        after_id=after_id,
        filters=parsed_filters,
    )

    # Check if there are more results
    has_more = len(task_message_entities) > limit
    task_message_entities = task_message_entities[:limit]

    # Build next cursor from last message
    next_cursor = None
    if has_more and task_message_entities:
        last_message = task_message_entities[-1]
        next_cursor = encode_cursor(last_message.id, last_message.created_at)

    messages = [TaskMessage.model_validate(entity) for entity in task_message_entities]

    return PaginatedMessagesResponse(
        data=messages,
        next_cursor=next_cursor,
        has_more=has_more,
    )


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
