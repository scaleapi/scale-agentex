from typing import List, Optional, Union


class GenericException(Exception):
    """Base class for all custom domain exceptions."""

    message: str
    code: int = 500  # default HTTP status code
    detail: str | None = None

    def __init__(
        self,
        message: str,
        code: int | None = None,
        detail: Optional[Union[str, List[str]]] = None,
    ):
        self.message = message
        if code is not None:
            self.code = code
        if detail is not None:
            self.detail = detail

    def __str__(self):
        return self.message

    def __repr__(self):
        return f"{self.__class__.__name__}: {self.message}"


class ClientError(GenericException):
    """Errors triggered by invalid client action (4xx)."""

    code = 400


class ServiceError(GenericException):
    """Errors triggered by downstream/internal failures (5xx)."""

    code = 500


class UnprocessableEntity(ClientError):
    """Errors triggered by invalid client shape"""

    code = 422
