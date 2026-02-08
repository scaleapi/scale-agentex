from src.domain.exceptions import ClientError


class DuplicateItemError(ClientError):
    """
    Exception raised when an item already exists in the database.
    """

    code = 400


class ItemDoesNotExist(ClientError):
    """
    Exception raised when an item does not exist in the database.
    """

    code = 404
