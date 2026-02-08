import builtins
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from enum import StrEnum
from typing import (
    Annotated,
    Any,
    Generic,
    Literal,
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
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.interfaces import LoaderOption
from sqlalchemy.sql import Select
from typing_extensions import TypeVar

from src.adapters.crud_store.exceptions import DuplicateItemError, ItemDoesNotExist
from src.adapters.crud_store.port import CRUDRepository
from src.adapters.orm import BaseORM
from src.config.dependencies import (
    DDatabaseAsyncReadOnlySessionMaker,
    DDatabaseAsyncReadWriteSessionMaker,
)
from src.domain.exceptions import ClientError, ServiceError
from src.utils.logging import make_logger
from src.utils.model_utils import BaseModel

logger = make_logger(__name__)

DUPLICATE_KEY_VAL_ERR = "duplicate key value"
CHECK_CONSTRAINT_ERR = "violates check constraint"
DEFAULT_LIST_LIMIT = 50


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


class EmptyRelationships(StrEnum):
    """Default empty relationships enum for repositories without relationships"""

    pass


Relationships = TypeVar(
    "Relationships",
    bound=StrEnum,
    default=EmptyRelationships,
)


class PostgresCRUDRepository(CRUDRepository[T], Generic[M, T, Relationships]):
    """
    Base PostgreSQL CRUD repository with support for optional relationship loading.

    Subclasses can define:
    - orm_class: The SQLAlchemy ORM model class
    - entity_class: The Pydantic entity class
    - relationships: StrEnum of available relationships (optional)
    - relationships_to_load_options: Dict mapping relationships to SQLAlchemy load options (optional)

    For backward compatibility, repositories without relationships can use the 2-parameter syntax:
        PostgresCRUDRepository[M, T]
    This automatically uses EmptyRelationships as the third parameter.
    """

    orm_class: type[M]
    entity_class: type[T]
    relationships: type[Relationships] = EmptyRelationships
    relationships_to_load_options: dict[Relationships, LoaderOption] = {}

    def __init_subclass__(cls) -> None:
        """Validate subclass configuration at class definition time"""
        super().__init_subclass__()

        # Only validate if relationships are defined
        if hasattr(cls, "relationships") and cls.relationships != EmptyRelationships:
            missing = [
                rel
                for rel in cls.relationships
                if rel not in cls.relationships_to_load_options
            ]
            if missing:
                raise TypeError(
                    f"{cls.__name__}: Missing loader options for relationships: {missing}"
                )

    @classmethod
    def _get_query_options(
        cls, relationships: list[Relationships] | None
    ) -> list[LoaderOption]:
        """Convert list of relationships to SQLAlchemy loader options"""
        if (
            not relationships
            or not hasattr(cls, "relationships")
            or cls.relationships == EmptyRelationships
        ):
            return []
        return [cls.relationships_to_load_options[rel] for rel in set(relationships)]

    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
        async_read_only_session_maker: DDatabaseAsyncReadOnlySessionMaker | None,
        orm: type[M],
        entity: type[T],
    ):
        self.async_rw_session_maker = async_read_write_session_maker
        # Fall back to read-write if read-only not provided (backward compatibility)
        self.async_ro_session_maker = (
            async_read_only_session_maker or async_read_write_session_maker
        )
        self.orm = orm
        self.entity = entity

    @asynccontextmanager
    async def start_async_db_session(
        self, allow_writes: bool = True
    ) -> AsyncGenerator[AsyncSession, None]:
        session_maker = (
            self.async_rw_session_maker if allow_writes else self.async_ro_session_maker
        )
        async with session_maker() as session:
            yield session

    async def create(self, item: T) -> T:
        """Create an item using INSERT ... RETURNING for single query efficiency.

        Uses RETURNING with explicit columns to avoid lazy-loading relationship
        attributes on the returned ORM object, which would fail outside async context.
        """
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            # Exclude None values to allow server defaults (e.g., created_at) to apply
            values = {k: v for k, v in item.to_dict().items() if v is not None}
            # Return only columns (not full ORM) to avoid lazy-loading relationships
            stmt = (
                insert(self.orm).values(**values).returning(*self.orm.__table__.columns)
            )
            result = await session.execute(stmt)
            row = result.one()
            await session.commit()
            return self.entity.model_validate(dict(row._mapping))

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

    async def get(
        self,
        id: str | None = None,
        name: str | None = None,
        relationships: list[Relationships] | None = None,
    ) -> T:
        async with (
            self.start_async_db_session(allow_writes=False) as session,
            async_sql_exception_handler(),
        ):
            result = await self._get(session, id, name, relationships=relationships)
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
            self.start_async_db_session(allow_writes=False) as session,
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
            self.start_async_db_session(allow_writes=False) as session,
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
        self,
        ids: list[str] | None = None,
        names: list[str] | None = None,
        relationships: list[Relationships] | None = None,
    ) -> list[T]:
        async with (
            self.start_async_db_session(allow_writes=False) as session,
            async_sql_exception_handler(),
        ):
            results = await self._batch_get(session, ids, names, relationships)
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
        limit: int | None = None,
        page_number: int | None = None,
        relationships: list[Relationships] | None = None,
    ) -> list[T]:
        async with (
            self.start_async_db_session(allow_writes=False) as session,
            async_sql_exception_handler(),
        ):
            if query is None:
                query = select(self.orm)

            if relationships:
                query = query.options(*self._get_query_options(relationships))

            order_by_clauses = self.create_order_by_clauses(
                order_by=order_by,
                order_direction="desc"
                if order_direction and order_direction.lower() == "desc"
                else "asc",
            )

            if order_by_clauses:
                query = query.order_by(*order_by_clauses)

            if filters:
                filter_conditions = self.create_where_clauses_from_filters(
                    filters=filters
                )
                if filter_conditions:
                    query = query.where(*filter_conditions)

            # Apply provided or default limit
            limit = limit or DEFAULT_LIST_LIMIT
            query = query.limit(limit)

            # Apply page number if provided
            if page_number is not None and page_number < 1:
                raise ClientError("Page number must be greater than 0")
            if page_number is not None:
                query = query.offset((page_number - 1) * limit)

            result = await session.execute(query)
            results = result.scalars()
            return [self.entity.model_validate(result) for result in results]

    async def _get(
        self,
        session: AsyncSession,
        id: str | None = None,
        name: str | None = None,
        relationships: builtins.list[Relationships] | None = None,
    ) -> M:
        query = select(self.orm)

        if relationships:
            query = query.options(*self._get_query_options(relationships))

        if id is not None:
            query = query.filter(self.orm.id == id)
        elif name is not None:
            query = query.filter(self.orm.name == name)
        else:
            raise ClientError("Either id or name must be provided.")

        result = await session.scalar(query)

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
        relationships: builtins.list[Relationships] | None = None,
    ) -> M:
        if ids is not None:
            query = select(self.orm).filter(self.orm.id.in_(ids))
        elif names is not None:
            query = select(self.orm).filter(self.orm.name.in_(names))
        else:
            raise ClientError("Either ids or names must be provided.")

        if relationships:
            query = query.options(*self._get_query_options(relationships))

        results = await session.execute(query)
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
