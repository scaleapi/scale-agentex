from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any

from temporalio.client import (
    Client,
    WorkflowExecution,
    WorkflowHandle,
)
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy


class TemporalGateway(ABC):
    """
    Interface for Temporal workflow orchestration operations.
    Provides abstraction over Temporal client operations for workflow and schedule management.
    """

    @abstractmethod
    async def start_workflow(
        self,
        workflow: str | type,
        workflow_id: str,
        args: list[Any] | None = None,
        task_queue: str | None = None,
        execution_timeout: timedelta | None = None,
        retry_policy: RetryPolicy | None = None,
        id_reuse_policy: WorkflowIDReusePolicy | None = None,
    ) -> WorkflowHandle:
        """
        Start a new workflow execution.

        Args:
            workflow: The workflow class or name to execute
            workflow_id: Unique identifier for the workflow execution
            args: Arguments to pass to the workflow
            task_queue: Task queue to use for the workflow
            execution_timeout: Maximum time for workflow execution
            retry_policy: Retry policy for the workflow
            id_reuse_policy: Policy for reusing workflow IDs

        Returns:
            Handle to the started workflow

        Raises:
            TemporalWorkflowError: If workflow fails to start
        """
        pass

    @abstractmethod
    async def get_workflow_handle(
        self,
        workflow_id: str,
        run_id: str | None = None,
        first_execution_run_id: str | None = None,
    ) -> WorkflowHandle:
        """
        Get a handle to an existing workflow.

        Args:
            workflow_id: The workflow ID
            run_id: Optional specific run ID
            first_execution_run_id: Optional first execution run ID

        Returns:
            Handle to the workflow

        Raises:
            TemporalWorkflowNotFoundError: If workflow doesn't exist
        """
        pass

    @abstractmethod
    async def signal_workflow(
        self,
        workflow_id: str,
        signal: str,
        arg: Any = None,
        run_id: str | None = None,
    ) -> None:
        """
        Send a signal to a running workflow.

        Args:
            workflow_id: The workflow ID to signal
            signal: The signal name
            arg: Optional argument to send with the signal
            run_id: Optional specific run ID

        Raises:
            TemporalWorkflowNotFoundError: If workflow doesn't exist
            TemporalSignalError: If signal fails
        """
        pass

    @abstractmethod
    async def query_workflow(
        self,
        workflow_id: str,
        query: str,
        arg: Any = None,
        run_id: str | None = None,
    ) -> Any:
        """
        Query a workflow for its current state.

        Args:
            workflow_id: The workflow ID to query
            query: The query name
            arg: Optional argument for the query
            run_id: Optional specific run ID

        Returns:
            The query result

        Raises:
            TemporalWorkflowNotFoundError: If workflow doesn't exist
            TemporalQueryError: If query fails
        """
        pass

    @abstractmethod
    async def cancel_workflow(
        self,
        workflow_id: str,
        run_id: str | None = None,
    ) -> None:
        """
        Cancel a running workflow.

        Args:
            workflow_id: The workflow ID to cancel
            run_id: Optional specific run ID

        Raises:
            TemporalWorkflowNotFoundError: If workflow doesn't exist
            TemporalCancelError: If cancellation fails
        """
        pass

    @abstractmethod
    async def terminate_workflow(
        self,
        workflow_id: str,
        reason: str | None = None,
        run_id: str | None = None,
    ) -> None:
        """
        Terminate a running workflow immediately.

        Args:
            workflow_id: The workflow ID to terminate
            reason: Optional reason for termination
            run_id: Optional specific run ID

        Raises:
            TemporalWorkflowNotFoundError: If workflow doesn't exist
            TemporalTerminateError: If termination fails
        """
        pass

    @abstractmethod
    async def describe_workflow(
        self,
        workflow_id: str,
        run_id: str | None = None,
    ) -> WorkflowExecution:
        """
        Get detailed information about a workflow execution.

        Args:
            workflow_id: The workflow ID
            run_id: Optional specific run ID

        Returns:
            Workflow execution details

        Raises:
            TemporalWorkflowNotFoundError: If workflow doesn't exist
        """
        pass

    @abstractmethod
    async def list_workflows(
        self,
        query: str | None = None,
        page_size: int = 100,
    ) -> list[WorkflowExecution]:
        """
        List workflow executions matching the query.

        Args:
            query: Optional query string to filter workflows
            page_size: Number of results per page

        Returns:
            List of workflow executions

        Raises:
            TemporalError: If listing fails
        """
        pass

    @abstractmethod
    async def get_client(self) -> Client:
        """
        Get the underlying Temporal client instance.

        Returns:
            The Temporal client

        Raises:
            TemporalConnectionError: If client is not connected
        """
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """
        Check if the Temporal client is connected and healthy.

        Returns:
            True if connected, False otherwise
        """
        pass
