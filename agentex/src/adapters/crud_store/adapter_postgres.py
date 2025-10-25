import builtins
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import (
    Annotated,
    Any,
    Generic,
    Literal,
    TypeVar,
)

from fastapi import Depends
from sqlalchemy import (
    ColumnExpressionArgument,
    UnaryExpression,
    asc,
    delete,
    desc,
    exc,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from src.adapters.crud_store.exceptions import DuplicateItemError, ItemDoesNotExist
from src.adapters.crud_store.port import CRUDRepository
from src.adapters.orm import BaseORM
from src.config.dependencies import DDatabaseAsyncReadWriteSessionMaker
from src.domain.exceptions import ClientError, ServiceError
from src.utils.logging import make_logger
from src.utils.model_utils import BaseModel

logger = make_logger(__name__)

DUPLICATE_KEY_VAL_ERR = "duplicate key value"
CHECK_CONSTRAINT_ERR = "violates check constraint"


@asynccontextmanager
async def async_sql_exception_handler():
    try:
        yield
    except exc.IntegrityError as e:
        # Handle SQLAlchemy exceptions here
        if DUPLICATE_KEY_VAL_ERR in str(e):
            raise DuplicateItemError(
                message="Item already exists. Please check all unique constraints and try again.",
                detail=str(e),
            ) from e
        else:
            raise ServiceError(
                message=f"Invalid input resulted in constraint violation: {e}",
                detail=str(e),
            ) from e
    except exc.NoResultFound as e:
        raise ItemDoesNotExist(
            message="No record found for given key", detail=str(e)
        ) from e
    except exc.NoForeignKeysError as e:
        raise ItemDoesNotExist(
            message="No foreign relationships found for given key", detail=str(e)
        ) from e
    except Exception as e:
        # only raising the exception currently since a ServerError will result in a code = 500, breaking existing behavior
        raise e


T = TypeVar("T", bound=BaseModel)
M = TypeVar("M", bound=BaseORM)


ColumnPrimitiveValue = str | int | float | bool | datetime | None


class PostgresCRUDRepository(CRUDRepository[T], Generic[M, T]):
    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
        orm: type[M],
        entity: type[T],
    ):
        self.async_rw_session_maker = async_read_write_session_maker
        self.orm = orm
        self.entity = entity

    @asynccontextmanager
    async def start_async_db_session(
        self, allow_writes: bool | None = True
    ) -> AsyncGenerator[AsyncSession, None]:
        if allow_writes:
            session_maker = self.async_rw_session_maker
        else:
            raise NotImplementedError("Read-only sessions are not yet supported.")
        async with session_maker() as session:
            yield session

    async def create(self, item: T) -> T:
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            orm = self.orm(**item.to_dict())
            session.add(orm)
            await session.commit()
            await session.refresh(orm)
            return self.entity.model_validate(orm)

    async def batch_create(self, items: list[T]) -> list[T]:
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            # Prepare a list of ORM instances from items
            orm_instances = [self.orm(**item.to_dict()) for item in items]
            session.add_all(orm_instances)
            await session.commit()

            # Refresh each instance to retrieve any auto-generated fields (like IDs)
            for orm_instance in orm_instances:
                await session.refresh(orm_instance)

            return [
                self.entity.model_validate(orm_instance)
                for orm_instance in orm_instances
            ]

    async def get(self, id: str | None = None, name: str | None = None) -> T:
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            result = await self._get(session, id, name)
            return self.entity.model_validate(result)

    async def get_by_field(self, field_name: str, field_value: Any) -> T | None:
        """
        Find a single item by a given field using an efficient single-row query.

        Args:
            field_name: The field name to search by
            field_value: The value to search for

        Returns:
            A single item matching the field criteria

        Raises:
            ItemDoesNotExist: If no item matches the criteria
            ClientError: If the field doesn't exist on the model
            ServiceError: If there's an error executing the query
        """
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            # Check if the field exists on the model
            if not hasattr(self.orm, field_name):
                raise ClientError(f"Field '{field_name}' does not exist on the model")

            # Handle list values for IN queries
            if isinstance(field_value, list):
                result = await session.scalar(
                    select(self.orm).filter(
                        getattr(self.orm, field_name).in_(field_value)
                    )
                )
            # Handle None values for IS NULL queries
            elif field_value is None:
                result = await session.scalar(
                    select(self.orm).filter(getattr(self.orm, field_name).is_(None))
                )
            # Handle regular equality comparisons
            else:
                result = await session.scalar(
                    select(self.orm).filter(
                        getattr(self.orm, field_name) == field_value
                    )
                )

            if result is None:
                raise ItemDoesNotExist(
                    f"Item with {field_name} '{field_value}' does not exist."
                )

            return self.entity.model_validate(result)

    async def find_by_field(self, field_name: str, field_value: Any) -> list[T]:
        """
        Find all items that match a given field value.

        Args:
            field_name: The field name to search by
            field_value: The value to search for

        Returns:
            A list of items matching the field criteria. Returns empty list if no matches found.

        Raises:
            ClientError: If the field doesn't exist on the model
            ServiceError: If there's an error executing the query
        """
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            # Check if the field exists on the model
            if not hasattr(self.orm, field_name):
                raise ClientError(f"Field '{field_name}' does not exist on the model")

            # Handle list values for IN queries
            if isinstance(field_value, list):
                query = select(self.orm).filter(
                    getattr(self.orm, field_name).in_(field_value)
                )
            # Handle None values for IS NULL queries
            elif field_value is None:
                query = select(self.orm).filter(getattr(self.orm, field_name).is_(None))
            # Handle regular equality comparisons
            else:
                query = select(self.orm).filter(
                    getattr(self.orm, field_name) == field_value
                )

            result = await session.execute(query)
            results = result.scalars().all()
            return [self.entity.model_validate(result) for result in results]

    async def batch_get(
        self, ids: list[str] | None = None, names: list[str] | None = None
    ) -> list[T]:
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            results = await self._batch_get(session, ids, names)
            return [self.entity.model_validate(result) for result in results]

    async def update(self, item: T) -> T:
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            orm = self.orm(**item.to_dict())
            modified_orm = await session.merge(orm)
            await session.commit()
            # Refreshing the object to ensure we have the latest data
            await session.refresh(modified_orm)
            return self.entity.model_validate(modified_orm)

    async def batch_update(self, items: list[T]) -> list[T]:
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            # Convert each item to a dictionary for bulk update
            update_data = [item.to_dict() for item in items]

            # Perform the bulk update by primary key
            await session.execute(update(self.orm), update_data)
            await session.commit()

            ids = [item.id for item in items]
            fresh_results = await session.scalars(
                select(self.orm).where(self.orm.id.in_(ids))
            )
            return [self.entity.model_validate(result) for result in fresh_results]

    async def delete(self, id: str | None = None, name: str | None = None) -> None:
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            # Ensure at least one of id or name is provided
            if not id and not name:
                raise ClientError("You must provide either id or name for deletion.")

            # Build the delete query
            if id:
                stmt = delete(self.orm).where(self.orm.id == id)
            elif name:
                stmt = delete(self.orm).where(self.orm.name == name)

            # Execute the delete statement
            await session.execute(stmt)
            await session.commit()

    async def batch_delete(
        self, ids: list[str] | None = None, names: list[str] | None = None
    ) -> None:
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            # Ensure at least one of ids or names is provided
            if not ids and not names:
                raise ClientError("You must provide either ids or names for deletion.")

            # Construct the delete query based on available criteria
            if ids:
                stmt = delete(self.orm).where(self.orm.id.in_(ids))
            elif names:
                stmt = delete(self.orm).where(self.orm.name.in_(names))

            # Execute the delete operation
            await session.execute(stmt)
            await session.commit()

    def create_order_by_clauses(
        self,
        order_by: str | None,
        order_direction: Literal["asc", "desc"],
    ) -> list[UnaryExpression[ColumnPrimitiveValue]]:
        """Create an ORDER BY clause for this ORM.

        Parameters
        ----------
        order_by : str | None
            The field to order by. If None, defaults to 'updated_at' then 'created_at' if available.
        order_direction : Literal["asc", "desc"]
            The direction to order by.

        Returns
        -------
        list[UnaryExpression[ColumnPrimitiveValue]]
            List of ORDER BY clauses. Empty list if no applicable columns.
        """

        order_func = desc if order_direction == "desc" else asc
        order_clauses: list[UnaryExpression[ColumnPrimitiveValue]] = []

        # If a specific order_by field is provided and exists, use it as primary sort
        if order_by and hasattr(self.orm, order_by):
            column = getattr(self.orm, order_by)
            order_clauses.append(order_func(column))

        # Add timestamp fields as secondary sort criteria
        if hasattr(self.orm, "updated_at"):
            order_clauses.append(order_func(self.orm.updated_at))
        if hasattr(self.orm, "created_at"):
            order_clauses.append(order_func(self.orm.created_at))

        return order_clauses

    def create_where_clauses_from_filters(
        self, filters: dict[str, ColumnPrimitiveValue | Sequence[ColumnPrimitiveValue]]
    ) -> list[ColumnExpressionArgument[bool]]:
        """Create a list of WHERE clauses from the provided filters for this ORM.

        Parameters
        ----------
        filters : dict[str, ColumnPrimitiveValue | Sequence[ColumnPrimitiveValue]]
            A dictionary of field names and their corresponding value or values to filter by.

        Returns
        -------
        list[ColumnExpressionArgument[bool]]
            A list of SQLAlchemy column expressions representing the WHERE clauses.
        """

        where_clauses: list[ColumnExpressionArgument[bool]] = []
        for field, value in filters.items():
            if hasattr(self.orm, field):
                if isinstance(value, Sequence) and not isinstance(value, str):
                    # filter on field by list of values
                    if None in value:
                        non_null_values = [v for v in value if v is not None]
                        if non_null_values:
                            # filter on field by list of values or NULL
                            where_clauses.append(
                                getattr(self.orm, field).is_(None)
                                | getattr(self.orm, field).in_(non_null_values)
                            )
                        else:
                            # filter on field matching NULL only
                            where_clauses.append(getattr(self.orm, field).is_(None))
                    else:
                        # filter on field by list of values
                        # do not match NULL
                        where_clauses.append(getattr(self.orm, field).in_(value))
                elif value is None:
                    # filter on field matching NULL only
                    where_clauses.append(getattr(self.orm, field).is_(None))
                else:
                    # filter on field by single value
                    where_clauses.append(getattr(self.orm, field) == value)
        return where_clauses

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        order_direction: Literal["asc", "desc"] | None = None,
        query: Select | None = None,
    ) -> list[T]:
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            if query is None:
                query = select(self.orm)

            order_by_clauses = self.create_order_by_clauses(
                order_by=order_by,
                order_direction="desc"
                if order_direction and order_direction.lower() == "desc"
                else "asc",
            )

            if order_by_clauses:
                query = query.order_by(*order_by_clauses)

            # Apply filters if provided
            if filters:
                filter_conditions = self.create_where_clauses_from_filters(
                    filters=filters
                )
                if filter_conditions:
                    query = query.where(*filter_conditions)

            # Execute the query
            result = await session.execute(query)
            results = result.scalars()
            return [self.entity.model_validate(result) for result in results]

    async def _get(
        self,
        session: AsyncSession,
        id: str | None = None,
        name: str | None = None,
    ) -> M:
        if id is not None:
            result = await session.scalar(select(self.orm).filter(self.orm.id == id))
        elif name is not None:
            result = await session.scalar(
                select(self.orm).filter(self.orm.name == name)
            )
        else:
            raise ClientError("Either id or name must be provided.")
        if result is None:
            if id is not None:
                error_message = f"Item with id '{id}' does not exist."
            else:
                error_message = f"Item with name '{name}' does not exist."
            raise ItemDoesNotExist(error_message)
        return result

    async def _batch_get(
        self,
        session: AsyncSession,
        ids: builtins.list[str] | None = None,
        names: builtins.list[str] | None = None,
    ) -> M:
        if ids is not None:
            results = await session.execute(
                select(self.orm).filter(self.orm.id.in_(ids))
            )
        elif names is not None:
            results = await session.execute(
                select(self.orm).filter(self.orm.name.in_(names))
            )
        else:
            raise ClientError("Either ids or names must be provided.")
        if results is None:
            if ids is not None:
                error_message = f"Item with id '{ids}' does not exist."
            else:
                error_message = f"Item with name '{names}' does not exist."
            raise ItemDoesNotExist(error_message)
        return results


DPostgresCRUDRepository = Annotated[
    PostgresCRUDRepository, Depends(PostgresCRUDRepository)
]
