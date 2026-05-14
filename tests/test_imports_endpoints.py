from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch


IMPORTS_BASE = "/api/v1/imports"


def _make_user(email: str, role: str = "superadmin", user_id: str = "64a1b2c3d4e5f6789012abcd"):
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


class TestImportEndpoints:
    def test_superadmin_can_upload_csv_import(self, client):
        users_collection = MagicMock()
        users_collection.find_one = AsyncMock(return_value=_make_user("superadmin@example.com"))

        imports_collection = MagicMock()
        imports_collection.delete_many = AsyncMock(return_value=MagicMock())
        imports_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="import-1"))
        imports_collection.find_one = AsyncMock(
            return_value={
                "_id": "import-1",
                "section_key": "home_trending",
                "section_label": "Trending home",
                "source": "retail",
                "category": "Informatique",
                "category_type": "top_category",
                "file_name": "products.csv",
                "imported_count": 1,
                "replace_existing": True,
                "imported_by_email": "superadmin@example.com",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "products": [
                    {
                        "id": "prod-1",
                        "name": "Produit import",
                        "brand": "Brand",
                        "bestPrice": 99.0,
                        "originalPrice": 120.0,
                        "image": "https://example.com/image.jpg",
                        "description": "Produit import",
                        "inStock": True,
                        "category": "Informatique",
                        "href": "https://example.com/product",
                        "shopPrices": [],
                        "specifications": None,
                    }
                ],
            }
        )

        auth_db = MagicMock()
        auth_db.users = users_collection
        auth_db.__getitem__.side_effect = lambda key: {
            "users": users_collection,
            "content_imports": imports_collection,
        }[key]

        csv_bytes = b"name,brand,best_price,image,product_url\nProduit import,Brand,99,https://example.com/image.jpg,https://example.com/product\n"

        with _override_auth_db(auth_db), patch(
            "app.api.endpoints.imports._imports_collection", return_value=imports_collection
        ):
            response = client.post(
                f"{IMPORTS_BASE}/upload",
                headers=_auth_header("superadmin@example.com"),
                files={"file": ("products.csv", BytesIO(csv_bytes), "text/csv")},
                data={
                    "section_key": "home_trending",
                    "category": "Informatique",
                    "replace_existing": "true",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["section_key"] == "home_trending"
        assert body["imported_count"] == 1

    def test_public_can_read_imported_section_data(self, client):
        imports_collection = MagicMock()
        imports_collection.find_one = AsyncMock(
            return_value={
                "_id": "import-1",
                "section_key": "appliance_showcase",
                "section_label": "Appliance showcase",
                "source": "retail",
                "category": "Réfrigérateur",
                "category_type": "top_category",
                "file_name": "appliance.csv",
                "imported_count": 1,
                "replace_existing": True,
                "imported_by_email": "superadmin@example.com",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "products": [],
            }
        )

        with patch("app.api.endpoints.imports._imports_collection", return_value=imports_collection):
            response = client.get(
                f"{IMPORTS_BASE}/section-data",
                params={"section_key": "appliance_showcase", "category": "Réfrigérateur"},
            )

        assert response.status_code == 200
        assert response.json()["section_label"] == "Appliance showcase"

    def test_public_can_read_imported_section_data_with_category_alias(self, client):
        imports_collection = MagicMock()
        imports_collection.find_one = AsyncMock(
            return_value={
                "_id": "import-2",
                "section_key": "appliance_showcase",
                "section_label": "Appliance showcase",
                "source": "retail",
                "category": "Réfrigérateur",
                "category_type": "top_category",
                "file_name": "fridge.csv",
                "imported_count": 1,
                "replace_existing": True,
                "imported_by_email": "superadmin@example.com",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "products": [],
            }
        )

        with patch("app.api.endpoints.imports._imports_collection", return_value=imports_collection):
            response = client.get(
                f"{IMPORTS_BASE}/section-data",
                params={"section_key": "appliance_showcase", "category": "RÃ©frigÃ©rateur"},
            )

        assert response.status_code == 200
        assert response.json()["category"] == "Réfrigérateur"

    def test_superadmin_can_delete_existing_import(self, client):
        users_collection = MagicMock()
        users_collection.find_one = AsyncMock(return_value=_make_user("superadmin@example.com"))

        imports_collection = MagicMock()
        imports_collection.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))

        auth_db = MagicMock()
        auth_db.users = users_collection
        auth_db.__getitem__.side_effect = lambda key: {
            "users": users_collection,
            "content_imports": imports_collection,
        }[key]

        with _override_auth_db(auth_db), patch(
            "app.api.endpoints.imports._imports_collection", return_value=imports_collection
        ):
            response = client.delete(
                f"{IMPORTS_BASE}/existing-import-id",
                headers=_auth_header("superadmin@example.com"),
            )

        assert response.status_code == 200
        assert response.json()["message"] == "Imported file deleted"
