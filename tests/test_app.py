"""
Unit tests for the FastAPI backend application.
Designed to run in a Jenkins CI/CD pipeline via:
    pytest tests/ -v --tb=short --junitxml=test-results.xml
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import timedelta, datetime, timezone

# ---------------------------------------------------------------------------
# 1. Configuration / Settings tests
# ---------------------------------------------------------------------------

class TestSettings:
    """Verify application settings load correctly."""

    def test_project_name(self):
        from app.core.config import settings
        assert settings.PROJECT_NAME == "FastAPI Backend"

    def test_api_prefix(self):
        from app.core.config import settings
        assert settings.API_V1_STR == "/api/v1"

    def test_algorithm_is_hs256(self):
        from app.core.config import settings
        assert settings.ALGORITHM == "HS256"

    def test_access_token_expiry_positive(self):
        from app.core.config import settings
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES > 0


# ---------------------------------------------------------------------------
# 2. Security utility tests
# ---------------------------------------------------------------------------

class TestSecurity:
    """Test password hashing and JWT token creation."""

    def test_password_hash_and_verify(self):
        from app.core.security import get_password_hash, verify_password
        plain = "SecureP@ss123"
        hashed = get_password_hash(plain)
        assert hashed != plain
        assert verify_password(plain, hashed) is True

    def test_password_verify_wrong_password(self):
        from app.core.security import get_password_hash, verify_password
        hashed = get_password_hash("CorrectPassword1")
        assert verify_password("WrongPassword1", hashed) is False

    def test_create_access_token_returns_string(self):
        from app.core.security import create_access_token
        token = create_access_token(subject="user@test.com")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_access_token_contains_subject(self):
        from app.core.security import create_access_token
        from jose import jwt
        from app.core.config import settings

        email = "user@test.com"
        token = create_access_token(subject=email)
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["sub"] == email

    def test_access_token_custom_expiry(self):
        from app.core.security import create_access_token
        from jose import jwt
        from app.core.config import settings

        token = create_access_token(
            subject="user@test.com",
            expires_delta=timedelta(minutes=60),
        )
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp > datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 3. Pydantic schema / model validation tests
# ---------------------------------------------------------------------------

class TestSchemas:
    """Validate Pydantic models used across the app."""

    def test_health_check_schema(self):
        from app.schemas.health import HealthCheck
        h = HealthCheck(status="ok", db_connected=True)
        assert h.status == "ok"
        assert h.db_connected is True

    def test_health_check_default_db_false(self):
        from app.schemas.health import HealthCheck
        h = HealthCheck(status="ok")
        assert h.db_connected is False

    def test_user_create_valid(self):
        from app.schemas.auth import UserCreate
        u = UserCreate(email="a@b.com", password="12345678")
        assert u.email == "a@b.com"
        assert u.role == "client"

    def test_user_create_short_password_rejected(self):
        from app.schemas.auth import UserCreate
        with pytest.raises(Exception):
            UserCreate(email="a@b.com", password="short")

    def test_user_create_invalid_email_rejected(self):
        from app.schemas.auth import UserCreate
        with pytest.raises(Exception):
            UserCreate(email="not-an-email", password="12345678")

    def test_user_login_schema(self):
        from app.schemas.auth import UserLogin
        u = UserLogin(email="a@b.com", password="secret")
        assert u.email == "a@b.com"

    def test_token_schema(self):
        from app.schemas.auth import Token
        t = Token(access_token="abc", token_type="bearer", role="client")
        assert t.access_token == "abc"

    def test_password_reset_schema(self):
        from app.schemas.auth import PasswordReset
        pr = PasswordReset(email="a@b.com", code="123456", new_password="newpass123")
        assert pr.code == "123456"

    def test_password_reset_short_code_rejected(self):
        from app.schemas.auth import PasswordReset
        with pytest.raises(Exception):
            PasswordReset(email="a@b.com", code="123", new_password="newpass123")

    def test_change_password_schema(self):
        from app.schemas.auth import ChangePassword
        cp = ChangePassword(current_password="old", new_password="newpass1234")
        assert cp.new_password == "newpass1234"

    def test_user_profile_update_partial(self):
        from app.schemas.auth import UserProfileUpdate
        up = UserProfileUpdate(full_name="John Doe")
        assert up.full_name == "John Doe"
        assert up.email is None

    def test_product_schema(self):
        from app.products.schemas import Product
        p = Product(
            id="sku123",
            name="Test Product",
            brand="TestBrand",
            bestPrice=19.99,
            image="http://img.jpg",
            description="A test product",
            inStock=True,
        )
        assert p.bestPrice == 19.99
        assert p.shopPrices == []

    def test_shop_price_schema(self):
        from app.products.schemas import ShopPrice
        sp = ShopPrice(shop="Amazon", price=9.99)
        assert sp.available is False
        assert sp.oldPrice is None

    def test_search_result_schema(self):
        from app.products.schemas import SearchResult
        sr = SearchResult(
            id="1", name="Widget", brand="Acme",
            bestPrice=5.0, image="http://img.png", inStock=True,
        )
        assert sr.name == "Widget"


class TestUserModel:
    """Validate the User document model."""

    def test_user_model_defaults(self):
        from app.models.user import User
        u = User(email="test@test.com", password_hash="hashed")
        assert u.role == "client"
        assert u.is_active is True
        assert u.is_verified is False

    def test_user_model_custom_role(self):
        from app.models.user import User
        u = User(email="admin@test.com", password_hash="x", role="admin")
        assert u.role == "admin"


# ---------------------------------------------------------------------------
# 4. API endpoint tests (using TestClient with mocked DB)
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Test the root-level health check."""

    def test_root_health_returns_200(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestAuthEndpoints:
    """Test auth routes with mocked database via FastAPI dependency override."""

    def _make_mock_db(self, find_one_return=None):
        mock_db = MagicMock()
        mock_db.users.find_one = AsyncMock(return_value=find_one_return)
        mock_db.users.insert_one = AsyncMock()
        return mock_db

    def _client_with_db(self, mock_db):
        """Return a TestClient whose get_auth_database dependency is overridden."""
        from app.main import app
        from app.db.mongodb import get_auth_database

        app.dependency_overrides[get_auth_database] = lambda: mock_db
        c = TestClient(app)
        yield c
        app.dependency_overrides.pop(get_auth_database, None)

    def test_signup_success(self, client):
        from app.main import app
        from app.db.mongodb import get_auth_database

        mock_db = self._make_mock_db(find_one_return=None)
        app.dependency_overrides[get_auth_database] = lambda: mock_db
        try:
            resp = client.post("/api/v1/auth/signup", json={
                "email": "new@user.com",
                "password": "securepass123",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["email"] == "new@user.com"
            assert data["role"] == "client"
        finally:
            app.dependency_overrides.pop(get_auth_database, None)

    def test_signup_duplicate_email(self, client):
        from app.main import app
        from app.db.mongodb import get_auth_database

        mock_db = self._make_mock_db(find_one_return={"email": "dup@user.com"})
        app.dependency_overrides[get_auth_database] = lambda: mock_db
        try:
            resp = client.post("/api/v1/auth/signup", json={
                "email": "dup@user.com",
                "password": "securepass123",
            })
            assert resp.status_code == 400
            assert "already registered" in resp.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_auth_database, None)

    def test_signup_invalid_payload(self, client):
        resp = client.post("/api/v1/auth/signup", json={
            "email": "not-email",
            "password": "short",
        })
        assert resp.status_code == 422

    def test_signin_wrong_password(self, client):
        from app.main import app
        from app.db.mongodb import get_auth_database
        from app.core.security import get_password_hash

        mock_db = self._make_mock_db(find_one_return={
            "_id": "abc",
            "email": "user@test.com",
            "password_hash": get_password_hash("correct_password"),
            "role": "client",
            "is_verified": True,
            "is_active": True,
        })
        app.dependency_overrides[get_auth_database] = lambda: mock_db
        try:
            resp = client.post("/api/v1/auth/signin", json={
                "email": "user@test.com",
                "password": "wrong_password",
            })
            assert resp.status_code in (400, 401, 403)
        finally:
            app.dependency_overrides.pop(get_auth_database, None)


class TestProductEndpoints:
    """Test product routes with mocked database."""

    @patch("app.products.service.get_categories", new_callable=AsyncMock)
    def test_get_categories(self, mock_get_cats, client):
        mock_get_cats.return_value = ["Electronics", "Clothing"]
        resp = client.get("/api/v1/products/categories")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @patch("app.products.service.get_random_products", new_callable=AsyncMock)
    def test_get_random_products(self, mock_random, client):
        mock_random.return_value = []
        resp = client.get("/api/v1/products/random?category=Electronics")
        assert resp.status_code == 200
        assert resp.json() == []

    @patch("app.products.service.get_product_by_sku", new_callable=AsyncMock)
    def test_get_product_by_sku_not_found(self, mock_sku, client):
        mock_sku.return_value = None
        resp = client.get("/api/v1/products/by-sku/NONEXIST")
        assert resp.status_code == 404

    @patch("app.products.service.search_products", new_callable=AsyncMock)
    def test_search_products_short_query(self, mock_search, client):
        resp = client.get("/api/v1/products/search?q=a")
        assert resp.status_code == 200
        assert resp.json() == []

    @patch("app.products.service.search_products", new_callable=AsyncMock)
    def test_search_products_valid(self, mock_search, client):
        mock_search.return_value = [
            {"id": "1", "name": "Widget", "brand": "Acme",
             "bestPrice": 5.0, "image": "http://img.png", "inStock": True}
        ]
        resp = client.get("/api/v1/products/search?q=widget")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# 5. Application setup tests
# ---------------------------------------------------------------------------

class TestAppSetup:
    """Verify FastAPI app is correctly configured."""

    def test_app_title(self):
        from app.main import app
        assert app.title == "FastAPI Backend"

    def test_cors_middleware_present(self):
        from app.main import app
        middleware_classes = [m.cls.__name__ for m in app.user_middleware]
        assert "CORSMiddleware" in middleware_classes

    def test_openapi_schema_exists(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "paths" in schema

    def test_registered_routes_include_products(self, client):
        resp = client.get("/openapi.json")
        paths = resp.json()["paths"]
        product_paths = [p for p in paths if "/products" in p]
        assert len(product_paths) > 0

    def test_registered_routes_include_auth(self, client):
        resp = client.get("/openapi.json")
        paths = resp.json()["paths"]
        auth_paths = [p for p in paths if "/auth" in p]
        assert len(auth_paths) > 0
