import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="session")
def simple_engine(postgres_url):
    """Create simple sync engine for testing"""
    # Use sync version of PostgreSQL
    sync_url = postgres_url  # Already in psycopg2 format
    engine = create_engine(sync_url, echo=True)
    yield engine
    engine.dispose()


@pytest.fixture
def simple_db_session(simple_engine):
    """Simple sync session for testing"""
    SessionLocal = sessionmaker(bind=simple_engine)
    session = SessionLocal()
    transaction = session.begin()
    try:
        yield session
    finally:
        transaction.rollback()
        session.close()
