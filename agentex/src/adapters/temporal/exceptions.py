from src.domain.exceptions import ClientError, ServiceError


class TemporalError(ServiceError):
    """Base exception for all Temporal-related errors."""

    code = 500


class TemporalConnectionError(ServiceError):
    """
    Exception raised when the Temporal service connection fails.
    This includes network issues, authentication failures, or service unavailability.
    """

    code = 503  # Service Unavailable


class TemporalWorkflowError(ServiceError):
    """
    Exception raised when a workflow operation fails.
    This is a general error for workflow-related issues.
    """

    code = 500


class TemporalWorkflowNotFoundError(ClientError):
    """
    Exception raised when attempting to access a workflow that doesn't exist.
    """

    code = 404


class TemporalWorkflowAlreadyExistsError(ClientError):
    """
    Exception raised when attempting to create a workflow with an ID that already exists.
    """

    code = 409  # Conflict


class TemporalSignalError(ServiceError):
    """
    Exception raised when sending a signal to a workflow fails.
    """

    code = 500


class TemporalQueryError(ServiceError):
    """
    Exception raised when querying a workflow fails.
    """

    code = 500


class TemporalCancelError(ServiceError):
    """
    Exception raised when cancelling a workflow fails.
    """

    code = 500


class TemporalTerminateError(ServiceError):
    """
    Exception raised when terminating a workflow fails.
    """

    code = 500


class TemporalScheduleError(ServiceError):
    """
    Exception raised when a schedule operation fails.
    This is a general error for schedule-related issues.
    """

    code = 500


class TemporalScheduleNotFoundError(ClientError):
    """
    Exception raised when attempting to access a schedule that doesn't exist.
    """

    code = 404


class TemporalScheduleAlreadyExistsError(ClientError):
    """
    Exception raised when attempting to create a schedule with an ID that already exists.
    """

    code = 409  # Conflict


class TemporalTimeoutError(ServiceError):
    """
    Exception raised when a Temporal operation times out.
    """

    code = 504  # Gateway Timeout


class TemporalInvalidArgumentError(ClientError):
    """
    Exception raised when invalid arguments are provided to a Temporal operation.
    """

    code = 400  # Bad Request
