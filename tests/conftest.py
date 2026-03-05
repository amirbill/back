import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment variables BEFORE importing the app
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/test")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client-id")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")

from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def mock_mongo():
    """Mock MongoDB connections so tests don't need a real database."""
    with patch("app.db.mongodb.connect_to_mongo", new_callable=AsyncMock) as mock_connect, \
         patch("app.db.mongodb.close_mongo_connection", new_callable=AsyncMock) as mock_close, \
         patch("app.db.mongodb.db") as mock_db:
        mock_db.client = MagicMock()
        yield {
            "connect": mock_connect,
            "close": mock_close,
            "db": mock_db,
        }


@pytest.fixture()
def client(mock_mongo):
    """Create a TestClient with mocked DB for each test."""
    from app.main import app
    with TestClient(app) as c:
        yield c
