from abc import ABC, abstractmethod
from typing import Generic, TypeVar

PrincipalT = TypeVar("PrincipalT")


class AuthenticationGateway(ABC, Generic[PrincipalT]):
    @abstractmethod
    async def verify_headers(self, headers: dict[str, str]) -> PrincipalT:
        """Raise AuthenticationError on failure; otherwise return principal context."""
        pass
