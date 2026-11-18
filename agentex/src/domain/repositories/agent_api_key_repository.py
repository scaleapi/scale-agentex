import builtins
from typing import Annotated

from fastapi import Depends
from sqlalchemy import delete, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.adapters.crud_store.adapter_postgres import (
    PostgresCRUDRepository,
    async_sql_exception_handler,
)
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.adapters.orm import AgentAPIKeyORM, AgentORM, SlackSocketModeAppORM
from src.config.dependencies import (
    DDatabaseAsyncReadOnlySessionMaker,
    DDatabaseAsyncReadWriteSessionMaker,
)
from src.domain.entities.agent_api_keys import (
    AgentAPIKeyEntity,
    AgentAPIKeyType,
    SlackSocketModeAppEntity,
)
from src.domain.entities.agents import AgentStatus
from src.utils.logging import make_logger

logger = make_logger(__name__)


async def _drop_deleted_agents_slack_app(
    session: AsyncSession, slack_app_id: str
) -> None:
    """Remove a Socket Mode row a soft-deleted agent left for this Slack app.

    Deleting an agent keeps its keys, and the app must stay registrable on another
    agent despite the unique constraint on the app id.
    """
    deleted_agents = select(AgentORM.id).where(AgentORM.status == AgentStatus.DELETED)
    await session.execute(
        delete(SlackSocketModeAppORM).where(
            SlackSocketModeAppORM.slack_app_id == slack_app_id,
            SlackSocketModeAppORM.agent_id.in_(deleted_agents),
        )
    )


class AgentAPIKeyRepository(PostgresCRUDRepository[AgentAPIKeyORM, AgentAPIKeyEntity]):
    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
        async_read_only_session_maker: DDatabaseAsyncReadOnlySessionMaker,
    ):
        super().__init__(
            async_read_write_session_maker,
            async_read_only_session_maker,
            AgentAPIKeyORM,
            AgentAPIKeyEntity,
        )

    async def list(
        self,
        filters: dict | None = None,
        limit: int | None = None,
        page_number: int | None = None,
    ) -> list[AgentAPIKeyEntity]:
        """
        List agent api_keys with optional filtering.

        Args:
            filters: Dictionary of filters to apply. Currently supports:
                    - agent_id: Filter agents by agent ID using the join table
        """
        query = select(AgentAPIKeyORM)
        if filters and "agent_id" in filters:
            query = query.join(AgentORM, AgentORM.id == AgentAPIKeyORM.agent_id).where(
                AgentORM.id == filters["agent_id"]
            )
        return await super().list(
            filters=filters, query=query, limit=limit, page_number=page_number
        )

    async def get_internal_api_key_by_agent_id(
        self, agent_id: str
    ) -> AgentAPIKeyEntity | None:
        """
        Get the internal API key for a given agent ID.

        Args:
            agent_id: The ID of the agent.

        Returns:
            An AgentAPIKeyEntity if found, otherwise None.
        """
        async with self.start_async_db_session(allow_writes=False) as session:
            # Build query with join to agents table
            query = (
                select(AgentAPIKeyORM)
                .join(AgentORM, AgentORM.id == AgentAPIKeyORM.agent_id)
                .where(
                    AgentORM.id == agent_id,
                    AgentAPIKeyORM.api_key_type == AgentAPIKeyType.INTERNAL,
                )
                .order_by(
                    AgentAPIKeyORM.created_at.desc()
                )  # Get the most recent internal key
                .limit(1)  # Limit to one result
            )

            result = await session.execute(query)
            row = result.scalars().first()
            return AgentAPIKeyEntity.model_validate(row) if row else None

    async def get_by_agent_id_and_name(
        self, agent_id: str, name: str, api_key_type: AgentAPIKeyType
    ) -> AgentAPIKeyEntity | None:
        """
        Get an agent API key by agent ID and name.

        Args:
            agent_id: The ID of the agent.
            name: The name of the API key.

        Returns:
            An AgentAPIKeyEntity if found, otherwise None.
        """
        async with self.start_async_db_session(allow_writes=False) as session:
            # Build query with join to agents table
            query = (
                select(AgentAPIKeyORM)
                .join(AgentORM, AgentORM.id == AgentAPIKeyORM.agent_id)
                .where(
                    AgentORM.id == agent_id,
                    AgentAPIKeyORM.name == name,
                    AgentAPIKeyORM.api_key_type == api_key_type,
                )
            )

            result = await session.execute(query)
            row = result.scalars().first()
            return AgentAPIKeyEntity.model_validate(row) if row else None

    async def get_by_agent_name_and_key_name(
        self, agent_name: str, key_name: str, api_key_type: AgentAPIKeyType
    ) -> AgentAPIKeyEntity | None:
        """
        Get an agent API key by agent name and key name.

        Args:
            agent_name: The name of the agent.
            key_name: The name of the API key.

        Returns:
            An AgentAPIKeyEntity if found, otherwise None.
        """
        async with self.start_async_db_session(allow_writes=False) as session:
            # Build query with join to agents table
            query = (
                select(AgentAPIKeyORM)
                .join(AgentORM, AgentORM.id == AgentAPIKeyORM.agent_id)
                .where(
                    AgentORM.name == agent_name,
                    AgentAPIKeyORM.name == key_name,
                    AgentAPIKeyORM.api_key_type == api_key_type,
                )
            )

            result = await session.execute(query)
            row = result.scalars().first()
            return AgentAPIKeyEntity.model_validate(row) if row else None

    async def get_external_by_agent_id_and_key(
        self, agent_id: str, api_key: str
    ) -> AgentAPIKeyEntity | None:
        """
        Get an agent API key by agent ID and API key.

        Args:
            agent_id: The ID of the agent.
            api_key: The API key.

        Returns:
            An AgentAPIKeyEntity if found, otherwise None.
        """
        async with self.start_async_db_session(allow_writes=False) as session:
            # Build query with join to agents table
            query = (
                select(AgentAPIKeyORM)
                .join(AgentORM, AgentORM.id == AgentAPIKeyORM.agent_id)
                .where(
                    AgentORM.id == agent_id,
                    AgentAPIKeyORM.api_key == api_key,
                    AgentAPIKeyORM.api_key_type == AgentAPIKeyType.EXTERNAL,
                )
            )

            result = await session.execute(query)
            row = result.scalars().first()
            return AgentAPIKeyEntity.model_validate(row) if row else None

    async def create_with_slack_socket_mode_app(
        self, item: AgentAPIKeyEntity, app: SlackSocketModeAppEntity
    ) -> AgentAPIKeyEntity:
        """Create a Slack trigger and its Socket Mode app row in one transaction.

        Raises:
            DuplicateItemError: A live agent already serves this Slack app.
        """
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            await _drop_deleted_agents_slack_app(session, app.slack_app_id)
            values = {k: v for k, v in item.to_dict().items() if v is not None}
            row = (
                await session.execute(
                    insert(AgentAPIKeyORM)
                    .values(**values)
                    .returning(*AgentAPIKeyORM.__table__.columns)
                )
            ).one()
            await session.execute(
                insert(SlackSocketModeAppORM).values(
                    **{k: v for k, v in app.to_dict().items() if v is not None}
                )
            )
            await session.commit()
            return AgentAPIKeyEntity.model_validate(dict(row._mapping))

    async def upsert_slack_socket_mode_app(
        self, app: SlackSocketModeAppEntity
    ) -> SlackSocketModeAppEntity:
        """Serve an existing trigger over Socket Mode, or replace its token and path.

        Raises:
            DuplicateItemError: A live agent's other trigger serves this Slack app.
        """
        async with (
            self.start_async_db_session(True) as session,
            async_sql_exception_handler(),
        ):
            await _drop_deleted_agents_slack_app(session, app.slack_app_id)
            values = {k: v for k, v in app.to_dict().items() if v is not None}
            row = (
                await session.execute(
                    pg_insert(SlackSocketModeAppORM)
                    .values(**values)
                    .on_conflict_do_update(
                        constraint="uq_slack_socket_mode_apps_agent_api_key",
                        set_={
                            "app_token_encrypted": app.app_token_encrypted,
                            "forward_path": app.forward_path,
                        },
                    )
                    .returning(*SlackSocketModeAppORM.__table__.columns)
                )
            ).one()
            await session.commit()
            return SlackSocketModeAppEntity.model_validate(dict(row._mapping))

    async def delete_slack_socket_mode_app(self, agent_api_key_id: str) -> bool:
        """Remove a trigger's Socket Mode row; False if it had none."""
        async with self.start_async_db_session(True) as session:
            result = await session.execute(
                delete(SlackSocketModeAppORM)
                .where(SlackSocketModeAppORM.agent_api_key_id == agent_api_key_id)
                .returning(SlackSocketModeAppORM.id)
            )
            deleted = result.first() is not None
            await session.commit()
            return deleted

    async def list_slack_socket_mode_apps(
        self, slack_app_id: str | None = None
    ) -> builtins.list[tuple[AgentAPIKeyEntity, SlackSocketModeAppEntity]]:
        """Socket Mode apps on agents that are not deleted, each with its trigger.

        Args:
            slack_app_id: Only this Slack app, if given.
        """
        async with self.start_async_db_session(allow_writes=False) as session:
            query = (
                select(AgentAPIKeyORM, SlackSocketModeAppORM)
                .join(
                    SlackSocketModeAppORM,
                    (SlackSocketModeAppORM.agent_api_key_id == AgentAPIKeyORM.id)
                    & (SlackSocketModeAppORM.agent_id == AgentAPIKeyORM.agent_id),
                )
                .join(AgentORM, AgentORM.id == AgentAPIKeyORM.agent_id)
                .where(AgentORM.status != AgentStatus.DELETED)
            )
            if slack_app_id is not None:
                query = query.where(SlackSocketModeAppORM.slack_app_id == slack_app_id)
            result = await session.execute(query)
            return [
                (
                    AgentAPIKeyEntity.model_validate(trigger),
                    SlackSocketModeAppEntity.model_validate(app),
                )
                for trigger, app in result.all()
            ]

    async def delete_by_agent_name_and_key_name(
        self, agent_name: str, key_name: str, api_key_type: AgentAPIKeyType
    ) -> None:
        """
        Delete an agent API key by agent name and key name.

        Args:
            agent_name: The name of the agent.
            key_name: The name of the API key.
        """
        api_key = await self.get_by_agent_name_and_key_name(
            agent_name, key_name, api_key_type
        )
        if api_key:
            await self.delete(api_key.id)
        else:
            error_msg = (
                f"API key with name '{key_name}' for agent '{agent_name}' not found."
            )
            logger.warning(error_msg)
            # Raise an exception if the API key does not exist
            # This is to ensure the caller knows the key was not found
            raise ItemDoesNotExist(error_msg)

    async def delete_by_agent_id_and_key_name(
        self, agent_id: str, key_name: str, api_key_type: AgentAPIKeyType
    ) -> None:
        """
        Delete an agent API key by agent ID and key name.

        Args:
            agent_id: The ID of the agent.
            key_name: The name of the API key.
        """
        api_key = await self.get_by_agent_id_and_name(agent_id, key_name, api_key_type)
        if api_key:
            await self.delete(api_key.id)
        else:
            error_msg = (
                f"API key with name '{key_name}' for agent ID '{agent_id}' not found."
            )
            logger.warning(error_msg)
            # Raise an exception if the API key does not exist
            # This is to ensure the caller knows the key was not found
            raise ItemDoesNotExist(error_msg)


DAgentAPIKeyRepository = Annotated[
    AgentAPIKeyRepository, Depends(AgentAPIKeyRepository)
]
