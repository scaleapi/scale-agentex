class GenericException(Exception):
    message: str
    code: int = 500  # Default code is 500
    detail: str = None

    def __init__(
        self, message: str, code: int = None, detail: str | list[str] | None = None
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
    """
    Raised when a client error occurs. Use this as an exception base class for all client
    exceptions.
    """

    code: int = 400


class ServiceError(GenericException):
    """
    Raised when an error that is not caused by bad user input occurs within the service
    """

    code: int = 500
