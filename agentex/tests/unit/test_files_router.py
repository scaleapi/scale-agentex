import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.api.routes.files import router
from src.adapters.storage.ports import StorageProvider
from src.config.storage_dependency import get_storage_provider

# Create a minimal app for testing the router
app = FastAPI()
app.include_router(router)

@pytest.fixture
def mock_storage():
    storage = MagicMock(spec=StorageProvider)
    storage.save_file = AsyncMock(return_value="test_file_id")
    return storage

@pytest.fixture
def client(mock_storage):
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    return TestClient(app)

def test_upload_valid_file(client, mock_storage):
    files = {'file': ('test.txt', b'Hello World', 'text/plain')}
    response = client.post("/files/upload", files=files)
    
    assert response.status_code == 201
    data = response.json()
    assert data["file_id"] == "test_file_id"
    assert data["name"] == "test.txt"
    assert data["size"] == 11
    assert data["type"] == "text/plain"
    
    # Verify save_file argument
    mock_storage.save_file.assert_called_once()

def test_upload_invalid_type(client):
    files = {'file': ('test.exe', b'Binary', 'application/x-msdownload')}
    response = client.post("/files/upload", files=files)
    assert response.status_code == 400
    assert "not allowed" in response.json()["message"]

def test_upload_empty_file(client):
    files = {'file': ('empty.txt', b'', 'text/plain')}
    response = client.post("/files/upload", files=files)
    assert response.status_code == 400
    assert "File is empty" in response.json()["message"]

def test_upload_too_large(client):
    # Mocking UploadFile.seek/tell might be hard with TestClient as it creates them.
    # But we can try to send a large body.
    # Generating 11MB string
    large_content = b"a" * (11 * 1024 * 1024)
    files = {'file': ('large.txt', large_content, 'text/plain')}
    response = client.post("/files/upload", files=files)
    assert response.status_code == 413
