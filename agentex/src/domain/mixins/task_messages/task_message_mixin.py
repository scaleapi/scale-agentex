import json
from typing import Any

from src.domain.entities.task_message_updates import DeltaType, TaskMessageDeltaEntity
from src.domain.entities.task_messages import (
    DataContentEntity,
    MessageAuthor,
    MessageStyle,
    ReasoningContentEntity,
    TaskMessageContentEntity,
    TaskMessageContentType,
    TextContentEntity,
    TextFormat,
    ToolRequestContentEntity,
    ToolResponseContentEntity,
)


class TaskMessageMixin:
    """Mixin for task message handling"""

    def parse_task_message(self, result: dict[str, Any]) -> TaskMessageContentEntity:
        """Parse a result dict into a TaskMessage"""

        message_type = result.get("content_type")
        if message_type == TaskMessageContentType.TEXT:
            return TextContentEntity.model_validate(result)
        elif message_type == TaskMessageContentType.DATA:
            return DataContentEntity.model_validate(result)
        elif message_type == TaskMessageContentType.TOOL_REQUEST:
            return ToolRequestContentEntity.model_validate(result)
        elif message_type == TaskMessageContentType.TOOL_RESPONSE:
            return ToolResponseContentEntity.model_validate(result)
        else:
            raise ValueError(f"Unknown message type: {message_type}")

    @staticmethod
    def create_initial_content_from_delta(
        delta: TaskMessageDeltaEntity,
    ) -> TaskMessageContentEntity:
        if delta.type == DeltaType.TEXT:
            return TextContentEntity(
                author=MessageAuthor.AGENT,
                content=delta.text_delta,
            )
        elif delta.type == DeltaType.DATA:
            return DataContentEntity(
                author=MessageAuthor.AGENT,
                data={},
            )
        elif delta.type == DeltaType.TOOL_REQUEST:
            return ToolRequestContentEntity(
                author=MessageAuthor.AGENT,
                tool_call_id=delta.tool_call_id,
                name=delta.name,
                arguments={},
            )
        elif delta.type == DeltaType.TOOL_RESPONSE:
            return ToolResponseContentEntity(
                author=MessageAuthor.AGENT,
                tool_call_id=delta.tool_call_id,
                name=delta.name,
                content=delta.content_delta,
            )
        elif (
            delta.type == DeltaType.REASONING_CONTENT
            or delta.type == DeltaType.REASONING_SUMMARY
        ):
            return ReasoningContentEntity(
                author=MessageAuthor.AGENT,
                summary=[delta.summary_delta]
                if delta.type == DeltaType.REASONING_SUMMARY
                else [],
                content=[delta.content_delta]
                if delta.type == DeltaType.REASONING_CONTENT
                else [],
            )
        else:
            raise ValueError(f"Unknown delta type: {delta.type}")

    def convert_aggregated_task_message_to_content(
        self,
        aggregated_content_str: str,
        content_type: TaskMessageContentType,
    ) -> TaskMessageContentEntity:
        if content_type == TaskMessageContentType.TEXT:
            return TextContentEntity(
                author=MessageAuthor.AGENT,
                content=aggregated_content_str,
                style=MessageStyle.STATIC,
                format=TextFormat.PLAIN,
            )
        else:
            try:
                result = json.loads(aggregated_content_str)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Failed to load aggregated content as JSON: {aggregated_content_str}"
                ) from e
            return self.parse_task_message(result)
