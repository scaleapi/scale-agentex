from src.domain.exceptions import ClientError, ServiceError


class AuthorizationError(ClientError):
    """Client lacks necessary permissions to access the requested resource."""

    code = 403  # Forbidden


class AuthorizationGatewayError(ServiceError):
    """The authorization gateway returned an invalid or unexpected response."""

    code = 502


class AuthorizationServiceUnavailableError(ServiceError):
    """The authorization service is unavailable or timed-out."""

    code = 503
