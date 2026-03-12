"""
Extended tests for app/api/endpoints/auth.py covering:
  - signin, verify-email, resend-verification, forgot-password,
    reset-password, /me, change-password.

Run with: pytest tests/test_auth_extended.py -v
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import contextmanager
from datetime import datetime, timedelta

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/test")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")

AUTH_BASE = "/api/v1/auth"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(email="alice@example.com", password_hash=None, role="client",
               verified=True, reset_code=None, reset_expires=None,
               user_id="64a1b2c3d4e5f6789012abcd"):
    from app.core.security import get_password_hash
    return {
        "_id": user_id,
        "email": email,
        "full_name": "Alice",
        "password_hash": password_hash or get_password_hash("Password1!"),
        "role": role,
        "is_verified": verified,
        "verification_code": "",
        "reset_code": reset_code,
        "reset_code_expires": reset_expires,
        "picture": None,
        "google_id": None,
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }


def _make_mock_db(find_one_return=None):
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=find_one_return)
    mock_db.users.insert_one = AsyncMock()
    mock_db.users.update_one = AsyncMock()
    return mock_db


@contextmanager
def _override_db(mock_db):
    """Context manager that overrides get_auth_database dependency."""
    from app.main import app
    from app.db.mongodb import get_auth_database
    app.dependency_overrides[get_auth_database] = lambda: mock_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_auth_database, None)


# ---------------------------------------------------------------------------
# Signin
# ---------------------------------------------------------------------------

class TestSignin:

    def test_signin_success(self, client):
        from app.core.security import get_password_hash
        user_doc = _make_user(email="bob@test.com",
                              password_hash=get_password_hash("Correct1!"))
        mock_db = _make_mock_db(find_one_return=user_doc)
        with _override_db(mock_db):
            resp = client.post(f"{AUTH_BASE}/signin",
                               json={"email": "bob@test.com", "password": "Correct1!"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_signin_wrong_password(self, client):
        from app.core.security import get_password_hash
        user_doc = _make_user(email="bob@test.com",
                              password_hash=get_password_hash("RealPass1!"))
        mock_db = _make_mock_db(find_one_return=user_doc)
        with _override_db(mock_db):
            resp = client.post(f"{AUTH_BASE}/signin",
                               json={"email": "bob@test.com", "password": "WrongPass1!"})
        assert resp.status_code == 400

    def test_signin_unknown_email(self, client):
        mock_db = _make_mock_db(find_one_return=None)
        with _override_db(mock_db):
            resp = client.post(f"{AUTH_BASE}/signin",
                               json={"email": "nobody@test.com", "password": "Abc123!"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Verify email
# ---------------------------------------------------------------------------

class TestVerifyEmail:

    def test_verify_email_success(self, client):
        user_doc = _make_user(verified=False)
        user_doc["verification_code"] = "654321"
        mock_db = _make_mock_db(find_one_return=user_doc)
        with _override_db(mock_db):
            resp = client.post(f"{AUTH_BASE}/verify-email",
                               json={"email": "alice@example.com", "code": "654321"})
        assert resp.status_code == 200
        assert "verified" in resp.json()["message"].lower()

    def test_verify_email_wrong_code(self, client):
        user_doc = _make_user(verified=False)
        user_doc["verification_code"] = "111111"
        mock_db = _make_mock_db(find_one_return=user_doc)
        with _override_db(mock_db):
            resp = client.post(f"{AUTH_BASE}/verify-email",
                               json={"email": "alice@example.com", "code": "999999"})
        assert resp.status_code == 400

    def test_verify_email_user_not_found(self, client):
        mock_db = _make_mock_db(find_one_return=None)
        with _override_db(mock_db):
            resp = client.post(f"{AUTH_BASE}/verify-email",
                               json={"email": "ghost@example.com", "code": "123456"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Resend verification
# ---------------------------------------------------------------------------

class TestResendVerification:

    def test_resend_verification_success(self, client):
        user_doc = _make_user(verified=False)
        mock_db = _make_mock_db(find_one_return=user_doc)
        with _override_db(mock_db), \
             patch("app.api.endpoints.auth.send_verification_email", new_callable=AsyncMock):
            resp = client.post(f"{AUTH_BASE}/resend-verification",
                               json={"email": "alice@example.com"})
        assert resp.status_code == 200

    def test_resend_verification_already_verified(self, client):
        user_doc = _make_user(verified=True)
        mock_db = _make_mock_db(find_one_return=user_doc)
        with _override_db(mock_db):
            resp = client.post(f"{AUTH_BASE}/resend-verification",
                               json={"email": "alice@example.com"})
        assert resp.status_code == 400

    def test_resend_verification_user_not_found(self, client):
        mock_db = _make_mock_db(find_one_return=None)
        with _override_db(mock_db):
            resp = client.post(f"{AUTH_BASE}/resend-verification",
                               json={"email": "nobody@example.com"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------

class TestForgotPassword:

    def test_forgot_password_user_exists(self, client):
        user_doc = _make_user()
        mock_db = _make_mock_db(find_one_return=user_doc)
        with _override_db(mock_db), \
             patch("app.api.endpoints.auth.send_reset_password_email", new_callable=AsyncMock):
            resp = client.post(f"{AUTH_BASE}/forgot-password",
                               json={"email": "alice@example.com"})
        assert resp.status_code == 200
        assert "message" in resp.json()

    def test_forgot_password_user_not_found_does_not_reveal(self, client):
        mock_db = _make_mock_db(find_one_return=None)
        with _override_db(mock_db):
            resp = client.post(f"{AUTH_BASE}/forgot-password",
                               json={"email": "ghost@example.com"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Reset password
# ---------------------------------------------------------------------------

class TestResetPassword:

    def test_reset_password_success(self, client):
        future = datetime.utcnow() + timedelta(minutes=10)
        user_doc = _make_user(reset_code="123456", reset_expires=future)
        mock_db = _make_mock_db(find_one_return=user_doc)
        with _override_db(mock_db):
            resp = client.post(f"{AUTH_BASE}/reset-password", json={
                "email": "alice@example.com",
                "code": "123456",
                "new_password": "NewSecure1!",
            })
        assert resp.status_code == 200

    def test_reset_password_wrong_code(self, client):
        future = datetime.utcnow() + timedelta(minutes=10)
        user_doc = _make_user(reset_code="111111", reset_expires=future)
        mock_db = _make_mock_db(find_one_return=user_doc)
        with _override_db(mock_db):
            resp = client.post(f"{AUTH_BASE}/reset-password", json={
                "email": "alice@example.com",
                "code": "999999",
                "new_password": "NewSecure1!",
            })
        assert resp.status_code == 400

    def test_reset_password_expired_code(self, client):
        past = datetime.utcnow() - timedelta(minutes=5)
        user_doc = _make_user(reset_code="123456", reset_expires=past)
        mock_db = _make_mock_db(find_one_return=user_doc)
        with _override_db(mock_db):
            resp = client.post(f"{AUTH_BASE}/reset-password", json={
                "email": "alice@example.com",
                "code": "123456",
                "new_password": "NewSecure1!",
            })
        assert resp.status_code == 400

    def test_reset_password_user_not_found(self, client):
        mock_db = _make_mock_db(find_one_return=None)
        with _override_db(mock_db):
            resp = client.post(f"{AUTH_BASE}/reset-password", json={
                "email": "ghost@example.com",
                "code": "123456",
                "new_password": "NewSecure1!",
            })
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /me endpoint
# ---------------------------------------------------------------------------

class TestMeEndpoint:

    def _auth_header(self, email="alice@example.com"):
        from app.core.security import create_access_token
        token = create_access_token(subject=email)
        return {"Authorization": f"Bearer {token}"}

    def test_me_returns_current_user(self, client):
        user_doc = _make_user(email="alice@example.com")
        mock_db = _make_mock_db(find_one_return=user_doc)
        with _override_db(mock_db):
            resp = client.get(f"{AUTH_BASE}/me", headers=self._auth_header())
        assert resp.status_code == 200
        assert resp.json()["email"] == "alice@example.com"

    def test_me_without_token_returns_401(self, client):
        resp = client.get(f"{AUTH_BASE}/me")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /change-password
# ---------------------------------------------------------------------------

class TestChangePassword:

    def _auth_header(self, email="alice@example.com"):
        from app.core.security import create_access_token
        token = create_access_token(subject=email)
        return {"Authorization": f"Bearer {token}"}

    def test_change_password_success(self, client):
        from app.core.security import get_password_hash
        user_doc = _make_user(email="alice@example.com",
                              password_hash=get_password_hash("OldPass1!"))
        mock_db = _make_mock_db(find_one_return=user_doc)
        with _override_db(mock_db):
            resp = client.put(f"{AUTH_BASE}/change-password",
                              headers=self._auth_header(),
                              json={"current_password": "OldPass1!", "new_password": "NewPass1!"})
        assert resp.status_code == 200

    def test_change_password_wrong_current(self, client):
        from app.core.security import get_password_hash
        user_doc = _make_user(email="alice@example.com",
                              password_hash=get_password_hash("RealPass1!"))
        mock_db = _make_mock_db(find_one_return=user_doc)
        with _override_db(mock_db):
            resp = client.put(f"{AUTH_BASE}/change-password",
                              headers=self._auth_header(),
                              json={"current_password": "WrongPass1!", "new_password": "NewPass1!"})
        assert resp.status_code == 400

