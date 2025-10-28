from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends

from src.adapters.crud_store.exceptions import DuplicateItemError, ItemDoesNotExist
from src.domain.entities.agents import ACPType, AgentEntity, AgentStatus
from src.domain.repositories.agent_repository import DAgentRepository
from src.domain.repositories.deployment_history_repository import (
    DDeploymentHistoryRepository,
)
from src.utils.ids import orm_id
from src.utils.logging import make_logger

logger = make_logger(__name__)


class AgentsUseCase:
    def __init__(
        self,
        agent_repository: DAgentRepository,
        deployment_history_repository: DDeploymentHistoryRepository,
    ):
        self.agent_repo = agent_repository
        self.deployment_history_repo = deployment_history_repository

    async def register_agent(
        self,
        name: str,
        description: str,
        acp_url: str,
        agent_id: str | None = None,
        acp_type: ACPType = ACPType.AGENTIC,
        registration_metadata: dict[str, Any] | None = None,
    ) -> AgentEntity:
        # If an agent_id is passed, then the agent expects that it is already in the db
        if agent_id:
            agent = await self.agent_repo.get(id=agent_id)
            # Update the agent with potentially new name/description (acp_url should never change)
            agent.name = name
            agent.description = description
            agent.status = AgentStatus.READY
            agent.status_reason = "Agent registered successfully."
            agent.acp_type = acp_type
            if registration_metadata:
                existing_metadata = agent.registration_metadata or {}
                existing_metadata.update(registration_metadata)
                agent.registration_metadata = existing_metadata
            agent.registered_at = datetime.now(UTC)
            agent = await self.agent_repo.update(item=agent)
        else:
            # If an agent_id is not passed, then its probably a new one. We should first validate by checking in the DB
            try:
                agent = await self.agent_repo.get(name=name)
                existing_agent_data = agent.model_dump()

                # Update agent fields
                agent.description = description
                agent.acp_url = acp_url
                agent.status = AgentStatus.READY
                agent.status_reason = "Agent registered successfully."
                agent.acp_type = acp_type
                if registration_metadata:
                    existing_metadata = agent.registration_metadata or {}
                    existing_metadata.update(registration_metadata)
                    agent.registration_metadata = existing_metadata

                # Check if any fields have changed by comparing model dumps
                updated_agent_data = agent.model_dump()
                has_changes = existing_agent_data != updated_agent_data

                if has_changes:
                    logger.info(
                        f"Agent {name} has changed, updating agent with new values: {updated_agent_data}"
                    )
                    agent.registered_at = datetime.now(UTC)
                    agent = await self.agent_repo.update(item=agent)
                    await self.maybe_update_agent_deployment_history(agent)
                else:
                    logger.info(f"Agent {name} has not changed, skipping update")
                return agent
            except ItemDoesNotExist:
                logger.info(f"Agent {name} not found, creating new agent")
                pass

            # Initialize a new agent
            agent = AgentEntity(
                id=orm_id(),
                name=name,
                description=description,
                status=AgentStatus.READY,
                status_reason="Agent registered successfully.",
                acp_url=acp_url,
                acp_type=acp_type,
                registration_metadata=registration_metadata,
                registered_at=datetime.now(UTC),
            )
            # This is a problem only if multiple pods spin up and then make a request all at the same time.
            # In that case, the first pod will create the agent and the rest should succeed silently
            try:
                agent = await self.agent_repo.create(item=agent)
            except DuplicateItemError:
                logger.info(
                    f"Agent {name} was likely created in parallel, skipping creation"
                )
        await self.maybe_update_agent_deployment_history(agent)
        return agent

    async def maybe_update_agent_deployment_history(self, agent: AgentEntity) -> None:
        try:
            await self.deployment_history_repo.create_from_agent(agent)
        except Exception as e:
            logger.error(
                f"Error creating deployment history entry for agent {agent.id}: {e}"
            )
            return

    async def get(self, id: str | None = None, name: str | None = None) -> AgentEntity:
        agent = await self.agent_repo.get(id=id, name=name)
        if agent.status == AgentStatus.DELETED:
            if id:
                raise ItemDoesNotExist(f"Agent {id} not found")
            else:
                raise ItemDoesNotExist(f"Agent {name} not found")
        return agent

    async def update(self, agent: AgentEntity) -> AgentEntity:
        return await self.agent_repo.update(item=agent)

    async def delete(
        self, id: str | None = None, name: str | None = None
    ) -> AgentEntity:
        agent = await self.agent_repo.get(id=id, name=name)
        if agent.status == AgentStatus.DELETED:
            if id:
                raise ItemDoesNotExist(f"Agent {id} not found")
            else:
                raise ItemDoesNotExist(f"Agent {name} not found")
        agent.status = AgentStatus.DELETED
        agent.status_reason = "Agent deleted successfully"
        await self.agent_repo.update(agent)
        return agent

    async def list(
        self,
        limit: int,
        page_number: int,
        task_id: str | None = None,
        **filters,
    ) -> list[AgentEntity]:
        if task_id is not None:
            filters["task_id"] = task_id

        return await self.agent_repo.list(
            filters=filters, limit=limit, page_number=page_number
        )


DAgentsUseCase = Annotated[AgentsUseCase, Depends(AgentsUseCase)]
