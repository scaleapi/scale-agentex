from abc import ABC, abstractmethod
from enum import Enum
from typing import Literal


class Method(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class HttpPort(ABC):
    @abstractmethod
    async def async_call(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        url: str,
        payload: dict | None = None,
    ) -> dict:
        pass

    @abstractmethod
    def call(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        url: str,
        payload: dict | None = None,
    ) -> dict:
        pass
