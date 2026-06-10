"""Test-only seeding use case.

Inserts resource rows directly into the repositories without going through the
ACP runtime. Mounted only when ENABLE_TEST_SEEDING is true AND
ENVIRONMENT != production. The endpoint that calls into this use case is gated
to the same conditions plus a shared-secret header. See
src/api/routes/test_seeding.py.

This module is deliberately isolated so it can be deleted in one surgical
removal when/if test seeding moves into a separate test-utilities image.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import Depends

from src.domain.entities.events import EventEntity
from src.domain.entities.task_messages import (
    DataContentEntity,
    MessageAuthor,
    TaskMessageContentEntity,
    TaskMessageContentType,
)
from src.domain.repositories.event_repository import DEventRepository
from src.utils.ids import orm_id
from src.utils.logging import make_logger

logger = make_logger(__name__)


class TestSeedingUseCase:  # noqa: PT001 — not a pytest class; "Test" prefix is the use-case domain name
    __test__ = False  # tell pytest not to collect this as a test class
    """Test-only resource seeding.

    Each `seed_<resource>` method writes a row directly via the matching
    repository, mirroring the persistence half of the natural-flow write path
    but skipping any downstream side effects (ACP forwards, etc.).

    NOTE on FGAC: events are not a first-class FGAC resource
    (AgentexResourceType has only agent/task/api_key/schedule). Event authz
    delegates to the parent agent. When seeding future FGAC-registered
    resources (task, api_key, schedule), the corresponding seed_* method MUST
    also call authorization_service.register_resource(...) before persisting,
    mirroring the pattern in agent_api_keys_use_case._register_api_key_in_auth.
    """

    def __init__(self, event_repository: DEventRepository) -> None:
        self.event_repository = event_repository

    async def seed_event(
        self,
        *,
        task_id: str,
        agent_id: str,
        content: dict[str, Any] | None = None,
        id_override: str | None = None,
        principal_id: str | None = None,
    ) -> EventEntity:
        """Seed a single event row.

        Injects an audit marker `{"seeded": true, "seeded_at": <iso8601>}` into
        the persisted content so downstream tests can filter for seeded rows.
        """
        event_id = id_override or orm_id()
        seeded_at = datetime.now(timezone.utc).isoformat()

        # Build the persisted content: start with any caller-supplied dict, then
        # overlay the audit marker. If no content was supplied, persist just the
        # marker as a DataContentEntity (events.content is nullable but we want
        # the marker to always be present, and DATA is the only content type
        # that accepts an arbitrary dict).
        merged: dict[str, Any] = dict(content) if content else {}
        merged["seeded"] = True
        merged["seeded_at"] = seeded_at

        # Seeded events are synthetic; mark them as agent-authored. The author
        # field is required by BaseTaskMessageContentEntity but has no
        # semantic meaning for seeded rows -- the {"seeded": true} audit
        # marker in `data` is the actual signal for downstream filtering.
        content_entity: TaskMessageContentEntity = DataContentEntity(
            type=TaskMessageContentType.DATA,
            author=MessageAuthor.AGENT,
            data=merged,
        )

        event = await self.event_repository.create(
            id=event_id,
            task_id=task_id,
            agent_id=agent_id,
            content=content_entity,
        )

        logger.info(
            "test seeding wrote resource",
            extra={
                "resource_type": "event",
                "resource_id": event.id,
                "principal_id": principal_id,
                "task_id": task_id,
                "agent_id": agent_id,
            },
        )

        # TODO when adding seed_task / seed_api_key / seed_schedule:
        # FGAC-registered resources MUST also call
        # authorization_service.register_resource(
        #     resource=AgentexResource.<type>(<id>),
        #     parent=AgentexResource.agent(<agent_id>),
        # )
        # BEFORE persisting, mirroring agent_api_keys_use_case._register_api_key_in_auth.
        # Events are exempt from this because event authz delegates to the parent
        # agent (which must already exist & already be registered).

        return event


DTestSeedingUseCase = Annotated[TestSeedingUseCase, Depends(TestSeedingUseCase)]
