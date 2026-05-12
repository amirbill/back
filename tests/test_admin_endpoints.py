"""
Tests for app/api/endpoints/admin.py.
"""
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from unittest.mock import patch


ADMIN_BASE = "/api/v1/admin"


def _make_user(email: str, role: str = "client", user_id: str = "64a1b2c3d4e5f6789012abcd"):
    return {
        "_id": user_id,
        "email": email,
        "password_hash": "hashed",
        "role": role,
        "full_name": "Test User",
        "is_verified": True,
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }


def _make_collection(find_one_side_effect=None):
    collection = MagicMock()
    collection.find_one = AsyncMock(side_effect=find_one_side_effect)
    collection.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=1))
    find_cursor = MagicMock()
    find_cursor.to_list = AsyncMock(return_value=[{"_id": "64a1b2c3d4e5f6789012abcd"}])
    collection.find.return_value = find_cursor
    return collection


def _make_db(users_collection, rules_collection=None):
    db = MagicMock()
    db.users = users_collection
    db.__getitem__.side_effect = lambda key: {
        "users": users_collection,
        "page_access_rules": rules_collection or MagicMock(),
    }[key]
    return db


@contextmanager
def _override_auth_db(mock_db):
    from app.main import app
    from app.db.mongodb import get_auth_database

    app.dependency_overrides[get_auth_database] = lambda: mock_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_auth_database, None)


@contextmanager
def _override_secondary_db(mock_db):
    from app.main import app
    from app.db.mongodb import get_database

    app.dependency_overrides[get_database] = lambda: mock_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_database, None)


@contextmanager
def _override_admin_collections(auth_users, secondary_users):
    with patch("app.api.endpoints.admin._users_collection", return_value=auth_users), patch(
        "app.api.endpoints.admin._secondary_users_collection", return_value=secondary_users
    ):
        yield


def _auth_header(email: str = "superadmin@example.com"):
    from app.core.security import create_access_token

    token = create_access_token(subject=email)
    return {"Authorization": f"Bearer {token}"}


class TestAdminRoleUpdates:
    def test_update_user_role_returns_200(self, client):
        current_superadmin = _make_user("superadmin@example.com", role="superadmin", user_id="superadmin-id")
        target_user = _make_user("target@example.com", role="client")
        updated_user = {**target_user, "role": "superadmin"}

        auth_users = _make_collection(
            find_one_side_effect=[
                current_superadmin,
                target_user,
                updated_user,
            ]
        )
        secondary_users = _make_collection(find_one_side_effect=[None, None])
        auth_db = _make_db(auth_users, MagicMock())
        secondary_db = _make_db(secondary_users)

        with _override_auth_db(auth_db), _override_secondary_db(secondary_db), _override_admin_collections(
            auth_users, secondary_users
        ):
            response = client.post(
                f"{ADMIN_BASE}/users/{target_user['_id']}/role",
                headers=_auth_header(),
                json={"role": "superadmin"},
            )

        assert response.status_code == 200
        assert response.json()["role"] == "superadmin"

    def test_update_user_role_returns_404_when_missing(self, client):
        current_superadmin = _make_user("superadmin@example.com", role="superadmin", user_id="superadmin-id")
        auth_users = _make_collection(find_one_side_effect=[current_superadmin, None, None])
        secondary_users = _make_collection(find_one_side_effect=[None, None])
        auth_db = _make_db(auth_users, MagicMock())
        secondary_db = _make_db(secondary_users)

        with _override_auth_db(auth_db), _override_secondary_db(secondary_db), _override_admin_collections(
            auth_users, secondary_users
        ):
            response = client.post(
                f"{ADMIN_BASE}/users/does-not-exist/role",
                headers=_auth_header(),
                json={"role": "superadmin"},
            )

        assert response.status_code == 404


class TestAdminUserDeletion:
    def test_delete_user_returns_200(self, client):
        current_superadmin = _make_user("superadmin@example.com", role="superadmin", user_id="superadmin-id")
        target_user = _make_user("target@example.com", role="client")

        auth_users = _make_collection(
            find_one_side_effect=[
                current_superadmin,
                target_user,
            ]
        )
        secondary_users = _make_collection(find_one_side_effect=[None])
        auth_db = _make_db(auth_users, MagicMock())
        secondary_db = _make_db(secondary_users)

        with _override_auth_db(auth_db), _override_secondary_db(secondary_db), _override_admin_collections(
            auth_users, secondary_users
        ):
            response = client.delete(
                f"{ADMIN_BASE}/users/{target_user['_id']}",
                headers=_auth_header(),
            )

        assert response.status_code == 200
        assert response.json()["message"] == "User deleted"

    def test_delete_user_rejects_self_delete(self, client):
        current_superadmin = _make_user("superadmin@example.com", role="superadmin", user_id="superadmin-id")

        auth_users = _make_collection(find_one_side_effect=[current_superadmin])
        secondary_users = _make_collection(find_one_side_effect=[None])
        auth_db = _make_db(auth_users, MagicMock())
        secondary_db = _make_db(secondary_users)

        with _override_auth_db(auth_db), _override_secondary_db(secondary_db), _override_admin_collections(
            auth_users, secondary_users
        ):
            response = client.delete(
                f"{ADMIN_BASE}/users/{current_superadmin['_id']}",
                headers=_auth_header(),
            )

        assert response.status_code == 403
