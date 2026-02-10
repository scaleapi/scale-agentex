#!/usr/bin/env python3
"""
Backfill task messages from MongoDB to PostgreSQL.

This script should be run BEFORE enabling dual-write phase to ensure
existing task messages are present in PostgreSQL.

Usage:
    python scripts/backfill_task_messages.py [--dry-run] [--batch-size=1000]

Options:
    --dry-run       Don't actually write to PostgreSQL, just log what would be done
    --batch-size    Number of records to process per batch (default: 1000)
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add the src directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy.ext.asyncio import async_sessionmaker
from src.config.dependencies import GlobalDependencies
from src.domain.repositories.task_message_postgres_repository import (
    TaskMessagePostgresRepository,
)
from src.domain.repositories.task_message_repository import TaskMessageRepository
from src.utils.logging import make_logger

logger = make_logger(__name__)


async def backfill_messages(
    dry_run: bool = False, batch_size: int = 1000
) -> tuple[int, int, int]:
    """
    Backfill all task messages from MongoDB to PostgreSQL.

    Args:
        dry_run: If True, don't actually write to PostgreSQL
        batch_size: Number of records to process per batch

    Returns:
        Tuple of (migrated_count, skipped_count, error_count)
    """
    # Initialize dependencies
    deps = GlobalDependencies()
    await deps.load()

    if deps.mongodb_database is None:
        logger.error("MongoDB is not configured. Cannot backfill.")
        return 0, 0, 0

    if deps.database_async_read_write_engine is None:
        logger.error("PostgreSQL is not configured. Cannot backfill.")
        return 0, 0, 0

    # Create repositories
    mongo_repo = TaskMessageRepository(deps.mongodb_database)

    rw_session_maker = async_sessionmaker(
        autoflush=False,
        bind=deps.database_async_read_write_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    ro_session_maker = async_sessionmaker(
        autoflush=False,
        bind=deps.database_async_read_only_engine
        or deps.database_async_read_write_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    postgres_repo = TaskMessagePostgresRepository(rw_session_maker, ro_session_maker)

    # Pagination through MongoDB
    page = 1
    total_migrated = 0
    total_skipped = 0
    total_errors = 0

    logger.info(f"Starting backfill (dry_run={dry_run}, batch_size={batch_size})")

    while True:
        try:
            messages = await mongo_repo.list(limit=batch_size, page_number=page)
        except Exception as e:
            logger.error(f"Error fetching messages from MongoDB: {e}")
            break

        if not messages:
            break

        for message in messages:
            try:
                # Check if already exists in PostgreSQL by ID
                try:
                    existing = await postgres_repo.get(id=message.id)
                except Exception:
                    existing = None

                if existing:
                    total_skipped += 1
                    continue

                if dry_run:
                    logger.info(
                        f"[DRY RUN] Would migrate message {message.id} "
                        f"(task={message.task_id})"
                    )
                    total_migrated += 1
                    continue

                # Create in PostgreSQL with the same ID
                await postgres_repo.create(message)
                total_migrated += 1

            except Exception as e:
                logger.error(
                    f"Error migrating message {message.id}: {e}",
                    extra={"task_id": message.task_id},
                )
                total_errors += 1

        logger.info(
            f"Processed page {page}: "
            f"migrated={total_migrated}, skipped={total_skipped}, errors={total_errors}"
        )
        page += 1

    logger.info(
        f"Backfill complete: "
        f"migrated={total_migrated}, skipped={total_skipped}, errors={total_errors}"
    )

    return total_migrated, total_skipped, total_errors


def main():
    parser = argparse.ArgumentParser(
        description="Backfill task messages from MongoDB to PostgreSQL"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually write to PostgreSQL, just log what would be done",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of records to process per batch (default: 1000)",
    )
    args = parser.parse_args()

    migrated, skipped, errors = asyncio.run(
        backfill_messages(dry_run=args.dry_run, batch_size=args.batch_size)
    )

    # Exit with error code if there were any errors
    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    # Import AsyncSession here to avoid issues with the path setup
    from sqlalchemy.ext.asyncio import AsyncSession

    main()
