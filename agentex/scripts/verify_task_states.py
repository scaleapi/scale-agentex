#!/usr/bin/env python3
"""
Verify consistency between MongoDB and PostgreSQL task states.

This script should be run during the dual_read phase to ensure data integrity
before switching to PostgreSQL-only storage.

Usage:
    python scripts/verify_task_states.py [--sample-size=1000] [--fix-discrepancies]

Options:
    --sample-size       Number of records to check (default: 1000, use 0 for all)
    --fix-discrepancies Fix discrepancies by syncing MongoDB data to PostgreSQL
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add the src directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy.ext.asyncio import async_sessionmaker
from src.config.dependencies import GlobalDependencies
from src.domain.repositories.task_state_postgres_repository import (
    TaskStatePostgresRepository,
)
from src.domain.repositories.task_state_repository import TaskStateRepository
from src.utils.logging import make_logger

logger = make_logger(__name__)


async def verify_states(
    sample_size: int = 1000, fix_discrepancies: bool = False
) -> dict:
    """
    Verify consistency between MongoDB and PostgreSQL task states.

    Args:
        sample_size: Number of records to check (0 for all)
        fix_discrepancies: If True, sync discrepancies from MongoDB to PostgreSQL

    Returns:
        Dictionary containing discrepancy information
    """
    # Initialize dependencies
    deps = GlobalDependencies()
    await deps.load()

    if deps.mongodb_database is None:
        logger.error("MongoDB is not configured. Cannot verify.")
        return {}

    if deps.database_async_read_write_engine is None:
        logger.error("PostgreSQL is not configured. Cannot verify.")
        return {}

    # Create repositories
    mongo_repo = TaskStateRepository(deps.mongodb_database)

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
    postgres_repo = TaskStatePostgresRepository(rw_session_maker, ro_session_maker)

    # Get sample from MongoDB
    limit = sample_size if sample_size > 0 else None
    try:
        mongo_states = await mongo_repo.list(limit=limit)
    except Exception as e:
        logger.error(f"Error fetching states from MongoDB: {e}")
        return {}

    discrepancies = {
        "missing_in_postgres": [],
        "state_mismatch": [],
        "fixed": [],
        "total_checked": len(mongo_states),
    }

    logger.info(f"Checking {len(mongo_states)} states...")

    for mongo_state in mongo_states:
        try:
            postgres_state = await postgres_repo.get(id=mongo_state.id)

            if postgres_state is None:
                discrepancies["missing_in_postgres"].append(
                    {
                        "id": mongo_state.id,
                        "task_id": mongo_state.task_id,
                        "agent_id": mongo_state.agent_id,
                    }
                )
                if fix_discrepancies:
                    try:
                        await postgres_repo.create(mongo_state)
                        discrepancies["fixed"].append(mongo_state.id)
                        logger.info(
                            f"Fixed: Created missing state {mongo_state.id} in PostgreSQL"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to fix missing state {mongo_state.id}: {e}"
                        )
                continue

            # Compare state content (deep comparison)
            if mongo_state.state != postgres_state.state:
                discrepancies["state_mismatch"].append(
                    {
                        "id": mongo_state.id,
                        "task_id": mongo_state.task_id,
                        "agent_id": mongo_state.agent_id,
                        "mongo_state_preview": _truncate_state(mongo_state.state),
                        "postgres_state_preview": _truncate_state(postgres_state.state),
                    }
                )
                if fix_discrepancies:
                    try:
                        postgres_state.state = mongo_state.state
                        await postgres_repo.update(postgres_state)
                        discrepancies["fixed"].append(mongo_state.id)
                        logger.info(
                            f"Fixed: Updated state content for {mongo_state.id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to fix state mismatch {mongo_state.id}: {e}"
                        )

        except Exception as e:
            logger.error(f"Error verifying state {mongo_state.id}: {e}")

    # Print summary
    _print_summary(discrepancies)

    return discrepancies


def _truncate_state(state: dict, max_length: int = 100) -> str:
    """Truncate state dict to a readable preview string."""
    if not state:
        return "{}"
    state_str = json.dumps(state)
    if len(state_str) > max_length:
        return state_str[:max_length] + "..."
    return state_str


def _print_summary(discrepancies: dict) -> None:
    """Print a summary of verification results."""
    print("\n" + "=" * 50)
    print("VERIFICATION SUMMARY")
    print("=" * 50)
    print(f"Total checked: {discrepancies['total_checked']}")
    print(f"Missing in PostgreSQL: {len(discrepancies['missing_in_postgres'])}")
    print(f"State mismatches: {len(discrepancies['state_mismatch'])}")
    print(f"Fixed: {len(discrepancies['fixed'])}")
    print("=" * 50)

    if discrepancies["missing_in_postgres"]:
        print("\nMissing in PostgreSQL (first 10):")
        for item in discrepancies["missing_in_postgres"][:10]:
            print(
                f"  - {item['id']} (task={item['task_id']}, agent={item['agent_id']})"
            )
        if len(discrepancies["missing_in_postgres"]) > 10:
            print(f"  ... and {len(discrepancies['missing_in_postgres']) - 10} more")

    if discrepancies["state_mismatch"]:
        print("\nState mismatches (first 10):")
        for item in discrepancies["state_mismatch"][:10]:
            print(f"  - {item['id']}")
            print(f"    MongoDB:    {item['mongo_state_preview']}")
            print(f"    PostgreSQL: {item['postgres_state_preview']}")
        if len(discrepancies["state_mismatch"]) > 10:
            print(f"  ... and {len(discrepancies['state_mismatch']) - 10} more")

    total_issues = len(discrepancies["missing_in_postgres"]) + len(
        discrepancies["state_mismatch"]
    )
    if total_issues == 0:
        print("\nAll states are consistent between MongoDB and PostgreSQL!")
    else:
        print(f"\nTotal issues found: {total_issues}")
        if not discrepancies["fixed"]:
            print("Run with --fix-discrepancies to sync from MongoDB to PostgreSQL")


def main():
    parser = argparse.ArgumentParser(
        description="Verify task state consistency between MongoDB and PostgreSQL"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=1000,
        help="Number of records to check (default: 1000, use 0 for all)",
    )
    parser.add_argument(
        "--fix-discrepancies",
        action="store_true",
        help="Fix discrepancies by syncing MongoDB data to PostgreSQL",
    )
    args = parser.parse_args()

    discrepancies = asyncio.run(
        verify_states(
            sample_size=args.sample_size, fix_discrepancies=args.fix_discrepancies
        )
    )

    # Exit with error code if there were unfixed discrepancies
    total_issues = len(discrepancies.get("missing_in_postgres", [])) + len(
        discrepancies.get("state_mismatch", [])
    )
    fixed = len(discrepancies.get("fixed", []))

    if total_issues > fixed:
        sys.exit(1)


if __name__ == "__main__":
    # Import AsyncSession here to avoid issues with the path setup
    from sqlalchemy.ext.asyncio import AsyncSession

    main()
