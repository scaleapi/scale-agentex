import pytest


@pytest.mark.unit
def test_smoke():
    """Smoke test to verify pytest setup works"""
    assert True


@pytest.mark.unit
def test_imports():
    """Verify we can import our main modules"""
    from src.domain.entities.agents import AgentEntity
    from src.domain.entities.tasks import TaskEntity

    assert AgentEntity is not None
    assert TaskEntity is not None
