from abc import ABC, abstractmethod
from typing import Annotated, Any, Generic, TypeVar

from fastapi import Depends

T = TypeVar("T")


class CRUDRepository(ABC, Generic[T]):
    @abstractmethod
    async def create(self, item: T) -> T:
        pass

    @abstractmethod
    async def batch_create(self, items: list[T]) -> list[T]:
        pass

    @abstractmethod
    async def get(self, id: str | None = None, name: str | None = None) -> T:
        pass

    @abstractmethod
    async def get_by_field(self, field_name: str, field_value: Any) -> T | None:
        pass

    @abstractmethod
    async def batch_get(
        self, ids: list[str] | None = None, names: list[str] | None = None
    ) -> list[T]:
        pass

    @abstractmethod
    async def update(self, item: T) -> T:
        pass

    @abstractmethod
    async def batch_update(self, items: list[T]) -> list[T]:
        pass

    @abstractmethod
    async def delete(self, id: str | None = None, name: str | None = None) -> None:
        pass

    @abstractmethod
    async def batch_delete(
        self, ids: list[str] | None = None, names: list[str] | None = None
    ) -> None:
        pass

    @abstractmethod
    async def list(self) -> list[T]:
        pass


DCRUDRepository = Annotated[CRUDRepository, Depends(CRUDRepository)]
