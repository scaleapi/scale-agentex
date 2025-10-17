from src.domain.exceptions import ClientError, ServiceError


class AuthenticationError(ClientError):
    """
    Exception raised when request was not successful because
    it lacks valid authentication credentials for the requested resource
    """

    code = 401


class AuthenticationGatewayError(ServiceError):
    """
    Exception raised when the authentication gateway itself is at fault
    (e.g. it returned an invalid response, forwarded garbage, or could not
    reach its upstream).
    """

    code = 502


class AuthenticationServiceUnavailableError(ServiceError):
    """
    Exception raised when the authentication service is temporarily
    unavailable or times out. Usually indicates maintenance, overload, or a
    network partition.
    """

    code = 503
