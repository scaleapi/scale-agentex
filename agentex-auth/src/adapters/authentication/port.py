from abc import ABC, abstractmethod
from typing import Any


class AuthenticationGateway(ABC):
    @abstractmethod
    async def verify_headers(self, headers: dict[str, str]) -> Any:
        """
        Verify authentication headers and return principal context.

        Raises:
            AuthenticationError: For authentication failures (401)
            AuthenticationGatewayError: For gateway errors (502)
            AuthenticationServiceUnavailableError: For service unavailable (503)
        """
        pass
