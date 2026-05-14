from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


NOTIFICATIONS_BASE = "/api/v1/notifications"


def _make_user(email: str, role: str = "client", user_id: str = "64a1b2c3d4e5f6789012abcd"):
    return {
        "_id": user_id,
        "email": email,
        "password_hash": "hashed",
        "role": role,
        "full_name": "Test User",
        "is_verified": True,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


def _auth_header(email: str):
    from app.core.security import create_access_token

    token = create_access_token(subject=email)
    return {"Authorization": f"Bearer {token}"}


@contextmanager
def _override_auth_db(mock_db):
    from app.main import app
    from app.db.mongodb import get_auth_database

    app.dependency_overrides[get_auth_database] = lambda: mock_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_auth_database, None)


class TestNotificationEndpoints:
    def test_superadmin_can_create_broadcast_notification(self, client):
        users_collection = MagicMock()
        users_collection.find_one = AsyncMock(return_value=_make_user("superadmin@example.com", role="superadmin"))

        notifications_collection = MagicMock()
        notifications_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="notif-1"))
        notifications_collection.find_one = AsyncMock(
            return_value={
                "_id": "notif-1",
                "text": "Promo sur ce produit",
                "product_id": "abc123",
                "product_name": "Produit test",
                "product_url": "/products/abc123?source=retail",
                "audience_roles": ["client", "admin"],
                "created_by_email": "superadmin@example.com",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "read_by": [],
            }
        )

        auth_db = MagicMock()
        auth_db.users = users_collection
        auth_db.__getitem__.side_effect = lambda key: {
            "users": users_collection,
            "notifications": notifications_collection,
        }[key]

        with _override_auth_db(auth_db), patch(
            "app.api.endpoints.notifications._notifications_collection", return_value=notifications_collection
        ):
            response = client.post(
                f"{NOTIFICATIONS_BASE}/broadcast",
                headers=_auth_header("superadmin@example.com"),
                json={
                    "text": "Promo sur ce produit",
                    "product_id": "abc123",
                    "product_name": "Produit test",
                    "product_url": "/products/abc123?source=retail",
                    "audience_roles": ["client", "admin"],
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["product_name"] == "Produit test"
        assert body["audience_roles"] == ["client", "admin"]

    def test_user_can_list_notifications_for_role(self, client):
        users_collection = MagicMock()
        users_collection.find_one = AsyncMock(return_value=_make_user("client@example.com", role="client"))

        notifications_collection = MagicMock()
        find_cursor = MagicMock()
        find_cursor.sort.return_value = find_cursor
        find_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": "notif-1",
                    "text": "Promo client",
                    "product_id": "abc123",
                    "product_name": "Produit test",
                    "product_url": "/products/abc123?source=retail",
                    "audience_roles": ["client", "admin"],
                    "created_by_email": "superadmin@example.com",
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                    "read_by": [],
                }
            ]
        )
        notifications_collection.find.return_value = find_cursor

        auth_db = MagicMock()
        auth_db.users = users_collection
        auth_db.__getitem__.side_effect = lambda key: {
            "users": users_collection,
            "notifications": notifications_collection,
        }[key]

        with _override_auth_db(auth_db), patch(
            "app.api.endpoints.notifications._notifications_collection", return_value=notifications_collection
        ):
            response = client.get(
                f"{NOTIFICATIONS_BASE}/me",
                headers=_auth_header("client@example.com"),
            )

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["is_read"] is False

    def test_mark_notification_as_read_updates_read_by(self, client):
        users_collection = MagicMock()
        users_collection.find_one = AsyncMock(return_value=_make_user("client@example.com", role="client"))

        notifications_collection = MagicMock()
        notifications_collection.update_one = AsyncMock(return_value=MagicMock())
        notifications_collection.find_one = AsyncMock(
            return_value={
                "_id": "notif-1",
                "text": "Promo client",
                "product_id": "abc123",
                "product_name": "Produit test",
                "product_url": "/products/abc123?source=retail",
                "audience_roles": ["client", "admin"],
                "created_by_email": "superadmin@example.com",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "read_by": ["client@example.com"],
            }
        )

        auth_db = MagicMock()
        auth_db.users = users_collection
        auth_db.__getitem__.side_effect = lambda key: {
            "users": users_collection,
            "notifications": notifications_collection,
        }[key]

        with _override_auth_db(auth_db), patch(
            "app.api.endpoints.notifications._notifications_collection", return_value=notifications_collection
        ):
            response = client.post(
                f"{NOTIFICATIONS_BASE}/notif-1/read",
                headers=_auth_header("client@example.com"),
            )

        assert response.status_code == 200
        assert response.json()["is_read"] is True
