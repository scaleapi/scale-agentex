from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from src.adapters.crud_store.adapter_postgres import (
    PostgresCRUDRepository,
)
from src.adapters.crud_store.exceptions import ItemDoesNotExist
from src.adapters.orm import AgentAPIKeyORM, AgentORM
from src.config.dependencies import DDatabaseAsyncReadWriteSessionMaker
from src.domain.entities.agent_api_keys import AgentAPIKeyEntity, AgentAPIKeyType
from src.utils.logging import make_logger

logger = make_logger(__name__)


class AgentAPIKeyRepository(PostgresCRUDRepository[AgentAPIKeyORM, AgentAPIKeyEntity]):
    def __init__(
        self,
        async_read_write_session_maker: DDatabaseAsyncReadWriteSessionMaker,
    ):
        super().__init__(
            async_read_write_session_maker,
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
        async with self.start_async_db_session(allow_writes=True) as session:
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
            agents = result.scalars().all()
            return AgentAPIKeyEntity.model_validate(agents[0]) if agents else None

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
        async with self.start_async_db_session(allow_writes=True) as session:
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
            agents = result.scalars().all()
            return AgentAPIKeyEntity.model_validate(agents[0]) if agents else None

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
        async with self.start_async_db_session(allow_writes=True) as session:
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
            agents = result.scalars().all()
            return AgentAPIKeyEntity.model_validate(agents[0]) if agents else None

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
        async with self.start_async_db_session(allow_writes=True) as session:
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
            agents = result.scalars().all()
            return AgentAPIKeyEntity.model_validate(agents[0]) if agents else None

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
