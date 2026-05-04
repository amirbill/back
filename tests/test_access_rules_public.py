from datetime import datetime
from unittest.mock import AsyncMock, MagicMock


def test_public_access_rules_endpoint_returns_rules(client):
    from app.main import app
    from app.api.endpoints import admin

    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(
        return_value=[
            {
                "_id": "rule-1",
                "path": "/dashboard/reports",
                "label": "Reports",
                "category": "Dashboard",
                "visible": True,
                "allowed_roles": ["admin"],
                "allowed_emails": ["report@example.com"],
                "updated_at": datetime.utcnow(),
            }
        ]
    )
    mock_collection = MagicMock()
    mock_collection.find.return_value.sort.return_value.sort.return_value = mock_cursor

    original_rules_collection = admin._rules_collection
    admin._rules_collection = lambda: mock_collection
    try:
        response = client.get("/api/v1/admin/access-rules/public")
    finally:
        admin._rules_collection = original_rules_collection

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["path"] == "/dashboard/reports"
