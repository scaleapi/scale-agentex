import pytest


@pytest.mark.unit
def test_postgres_fixtures_exist(postgres_url, postgres_container):
    """Test that container fixtures work"""
    assert postgres_url is not None
    assert postgres_container is not None
    print(f"URL: {postgres_url}")
