from src.domain.entities.task_message_updates import DeltaType, TaskMessageDeltaEntity
from src.domain.entities.task_messages import (
    DataContentEntity,
    MessageAuthor,
    ReasoningContentEntity,
    TaskMessageContentEntity,
    TextContentEntity,
    ToolRequestContentEntity,
    ToolResponseContentEntity,
)


class TaskMessageMixin:
    """Mixin for task message handling"""

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
