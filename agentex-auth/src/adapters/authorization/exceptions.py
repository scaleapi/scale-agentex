from src.domain.exceptions import ClientError, ServiceError


class AuthorizationError(ClientError):
    """
    Exception raised when request was not successful because
    the client lacks necessary permissions for the requested resource
    """

    code = 403


class AuthorizationGatewayError(ServiceError):
    """
    Exception raised when the authorization gateway itself is at fault
    (e.g. it returned an invalid response, forwarded garbage, or could not
    reach its upstream).
    """

    code = 502


class AuthorizationServiceUnavailableError(ServiceError):
    """
    Exception raised when the authorization service is temporarily
    unavailable or times out. Usually indicates maintenance, overload, or a
    network partition.
    """

    code = 503


class AuthorizationUnauthorizedError(ClientError):
    """
    Exception raised when the authorization service returns a 401 status code.
    """

    code = 401
