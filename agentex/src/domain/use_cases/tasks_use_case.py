from typing import Annotated, Any

from fastapi import Depends

from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.domain.entities.tasks import TaskEntity, TaskRelationships, TaskStatus
from src.domain.exceptions import ClientError
from src.domain.services.task_service import DAgentTaskService
from src.utils.logging import make_logger

logger = make_logger(__name__)


class _Unset:
    """Sentinel: PATCH field omitted (untouched) vs. explicitly null (cleared)."""


UNSET: Any = _Unset()


class TasksUseCase:
    """
    Use case for managing tasks. Handles CRUD operations and delegates task operations to ACP servers.
    """

    def __init__(
        self,
        task_service: DAgentTaskService,
    ):
        self.task_service = task_service

    async def get_task(
        self,
        id: str | None = None,
        name: str | None = None,
        relationships: list[TaskRelationships] | None = None,
    ) -> TaskEntity:
        """Get task details and current state from ACP server"""
        if not id and not name:
            raise ClientError("Either id or name must be provided")

        task = await self.task_service.get_task(
            id=id, name=name, relationships=relationships
        )
        if task.status == TaskStatus.DELETED:
            if id:
                raise ItemDoesNotExist(f"Task {id} not found")
            else:
                raise ItemDoesNotExist(f"Task {name} not found")
        return task

    async def update_task(self, task: TaskEntity) -> TaskEntity:
        """Update task record in repository"""
        if task.status == TaskStatus.DELETED:
            raise ItemDoesNotExist(f"Task {task.id} not found")
        return await self.task_service.update_task(task=task)

    async def delete_task(self, id: str | None = None, name: str | None = None) -> None:
        """Delete task record from repository"""
        # TODO: Should we notify ACP server about deletion?
        task = await self.task_service.get_task(id=id, name=name)
        if task.status == TaskStatus.DELETED:
            if id:
                raise ItemDoesNotExist(f"Task {id} not found")
            else:
                raise ItemDoesNotExist(f"Task {name} not found")
        task.status = TaskStatus.DELETED
        task.status_reason = "Task deleted successfully"
        await self.task_service.update_task(task=task)

    async def list_tasks(
        self,
        *,
        limit: int,
        page_number: int,
        id: str | list[str] | None = None,
        agent_id: str | None = None,
        agent_name: str | None = None,
        status: TaskStatus | list[TaskStatus] | None = None,
        task_metadata: dict | None = None,
        order_by: str | None = None,
        order_direction: str = "desc",
        relationships: list[TaskRelationships] | None = None,
    ) -> list[TaskEntity]:
        """List all tasks from repository"""
        return await self.task_service.list_tasks(
            id=id,
            agent_id=agent_id,
            agent_name=agent_name,
            status=status,
            task_metadata=task_metadata,
            limit=limit,
            page_number=page_number,
            order_by=order_by,
            order_direction=order_direction,
            relationships=relationships,
        )

    async def update_mutable_fields_on_task(
        self,
        id: str | None = None,
        name: str | None = None,
        task_metadata: dict[str, Any] | None = None,
        merge_params: dict[str, Any] | None = None,
        current_state: str | None | _Unset = UNSET,
    ) -> TaskEntity:
        """Update mutable fields on a task. ``current_state`` uses the UNSET sentinel
        (explicit null clears, omitted leaves it); ``task_metadata`` None means "not supplied".
        """

        if not id and not name:
            raise ClientError("Either id or name must be provided")

        current_state_supplied = not isinstance(current_state, _Unset)

        # todo: make this a transaction?
        task_entity = await self.task_service.get_task(id=id, name=name)
        if task_entity.status == TaskStatus.DELETED:
            if id:
                raise ItemDoesNotExist(f"Task {id} not found")
            else:
                raise ItemDoesNotExist(f"Task {name} not found")

        # No-op if no mutable field was supplied.
        if (
            task_metadata is None
            and merge_params is None
            and not current_state_supplied
        ):
            return task_entity

        # Atomic JSONB shallow-merge; run first so its refreshed entity is the fallback return.
        if merge_params:
            merged = await self.task_service.merge_task_params(
                task_entity.id, merge_params
            )
            if merged is not None:
                task_entity = merged

        # Single column-scoped write → one task_updated publish, no whole-row clobber.
        fields: dict[str, Any] = {}
        if task_metadata is not None:
            fields["task_metadata"] = task_metadata
        if current_state_supplied:
            fields["current_state"] = current_state
        if fields:
            updated = await self.task_service.update_mutable_fields(
                task_entity.id, fields
            )
            if updated is None:
                # Row vanished mid-flight (defensive; no live hard-delete path). Raise, don't return stale.
                raise ItemDoesNotExist(f"Task {id or name} not found")
            task_entity = updated

        return task_entity

    # Non-terminal statuses a task can be transitioned to a terminal status from.
    # RUNNING is the normal case; INTERRUPTED is also valid so an interrupted
    # (paused, still-continuable) task can still be canceled/completed/etc later.
    _TERMINAL_TRANSITION_SOURCES = (TaskStatus.RUNNING, TaskStatus.INTERRUPTED)

    async def _transition_to_terminal(
        self,
        target_status: TaskStatus,
        id: str | None = None,
        name: str | None = None,
        reason: str | None = None,
    ) -> TaskEntity:
        """Atomically transition a running or interrupted task to a terminal status."""
        if not id and not name:
            raise ClientError("Either id or name must be provided")

        task_entity = await self.task_service.get_task(id=id, name=name)
        if task_entity.status == TaskStatus.DELETED:
            raise ItemDoesNotExist(f"Task {id or name} not found")
        if task_entity.status not in self._TERMINAL_TRANSITION_SOURCES:
            raise ClientError(
                f"Task {task_entity.id} cannot be transitioned (current status: {task_entity.status}). "
                f"Only running or interrupted tasks can have their status updated."
            )

        # Compare-and-swap on the observed non-terminal source status (RUNNING or
        # INTERRUPTED) so a concurrent modification is still detected as a lost race.
        expected_status = task_entity.status
        status_reason = reason or f"Task {target_status.value.lower()}"
        updated = await self.task_service.transition_task_status(
            task_id=task_entity.id,
            expected_status=expected_status,
            new_status=target_status,
            status_reason=status_reason,
        )
        if updated is None:
            raise ClientError(
                f"Task {task_entity.id} status was concurrently modified. "
                f"Please retry the request."
            )
        return updated

    async def interrupt_task(
        self, id: str | None = None, name: str | None = None, reason: str | None = None
    ) -> TaskEntity:
        """Interrupt a running task without terminating it.

        This is the non-terminal counterpart to the terminal-transition methods
        (cancel/complete/fail/...): it transitions RUNNING -> INTERRUPTED via a
        compare-and-swap and deliberately does NOT go through
        _transition_to_terminal. The task stays continuable; the next message or
        event resumes it back to RUNNING.
        """
        if not id and not name:
            raise ClientError("Either id or name must be provided")

        task_entity = await self.task_service.get_task(id=id, name=name)
        if task_entity.status == TaskStatus.DELETED:
            raise ItemDoesNotExist(f"Task {id or name} not found")
        if task_entity.status != TaskStatus.RUNNING:
            raise ClientError(
                f"Task {task_entity.id} is not running (current status: {task_entity.status}). "
                f"Only running tasks can be interrupted."
            )

        status_reason = reason or "Task interrupted"
        updated = await self.task_service.transition_task_status(
            task_id=task_entity.id,
            expected_status=TaskStatus.RUNNING,
            new_status=TaskStatus.INTERRUPTED,
            status_reason=status_reason,
        )
        if updated is None:
            raise ClientError(
                f"Task {task_entity.id} status was concurrently modified. "
                f"Please retry the request."
            )
        return updated

    async def complete_task(
        self, id: str | None = None, name: str | None = None, reason: str | None = None
    ) -> TaskEntity:
        """Mark a running task as completed."""
        return await self._transition_to_terminal(
            TaskStatus.COMPLETED, id=id, name=name, reason=reason
        )

    async def fail_task(
        self, id: str | None = None, name: str | None = None, reason: str | None = None
    ) -> TaskEntity:
        """Mark a running task as failed."""
        return await self._transition_to_terminal(
            TaskStatus.FAILED, id=id, name=name, reason=reason
        )

    async def cancel_task(
        self, id: str | None = None, name: str | None = None, reason: str | None = None
    ) -> TaskEntity:
        """Mark a running task as canceled."""
        return await self._transition_to_terminal(
            TaskStatus.CANCELED, id=id, name=name, reason=reason
        )

    async def terminate_task(
        self, id: str | None = None, name: str | None = None, reason: str | None = None
    ) -> TaskEntity:
        """Mark a running task as terminated."""
        return await self._transition_to_terminal(
            TaskStatus.TERMINATED, id=id, name=name, reason=reason
        )

    async def timeout_task(
        self, id: str | None = None, name: str | None = None, reason: str | None = None
    ) -> TaskEntity:
        """Mark a running task as timed out."""
        return await self._transition_to_terminal(
            TaskStatus.TIMED_OUT, id=id, name=name, reason=reason
        )


DTaskUseCase = Annotated[TasksUseCase, Depends(TasksUseCase)]
