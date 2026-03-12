"""
Integration tests for app/products/router.py

All service-layer functions are mocked so no real DB is needed.
Tests exercise every endpoint in the products router via the FastAPI TestClient.

Run with:  pytest tests/test_products_router.py -v
"""
import os
import pytest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/test")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")

from fastapi.testclient import TestClient  # noqa: F401 – used by conftest fixture

# ---------------------------------------------------------------------------
# Shared sample data (mirrors what service functions return)
# ---------------------------------------------------------------------------

SAMPLE_PRODUCT = {
    "id": "64abc123",
    "name": "Laptop Pro 15",
    "brand": "BRAND_A",
    "bestPrice": 1400.0,
    "originalPrice": 1800.0,
    "image": "https://mytek.tn/img/laptop.jpg",
    "description": "Laptop Pro 15",
    "inStock": True,
    "category": "laptops",
    "shopPrices": [
        {
            "shop": "Tunisianet",
            "price": 1400.0,
            "oldPrice": None,
            "available": False,
            "url": "https://tunisianet.tn/laptop",
        },
        {
            "shop": "Mytek",
            "price": 1500.0,
            "oldPrice": 1800.0,
            "available": True,
            "url": "https://mytek.tn/laptop",
        },
    ],
    "specifications": None,
}

SAMPLE_SEARCH_RESULT = {
    "id": "64abc123",
    "name": "Laptop Pro 15",
    "brand": "BRAND_A",
    "bestPrice": 1400.0,
    "image": "https://mytek.tn/img/laptop.jpg",
    "inStock": True,
}

SAMPLE_ANALYTICS = {
    "category": "laptops",
    "cheapest_shop": "tunisianet",
    "cheapest_avg_price": 1350.50,
    "only_available": True,
    "shop_rankings": [
        {
            "shop": "tunisianet",
            "avg_price": 1350.50,
            "min_price": 1200.0,
            "max_price": 1500.0,
            "product_count": 42,
        }
    ],
}

SAMPLE_FAKE_PROMO = {
    "id": "64promo1",
    "title": "Fake Deal TV",
    "brand": "SamsungTV",
    "shop": "mytek",
    "image": "/placeholder.svg",
    "url": "https://mytek.tn/tv",
    "old_scrap_price": 800,
    "new_scrap_price": 799,
    "old_scrap_old_price": 1200,
    "price_change": -1,
    "price_change_pct": -0.1,
    "real_increase": 200,
    "real_increase_pct": 25.0,
    "old_price_inflated_by": 400,
    "old_price_inflated_by_pct": 50.0,
    "advertised_discount": 400,
    "advertised_discount_pct": 33.3,
    "verdict": "fake_promo",
    "top_category": "TV",
    "subcategory": "televisions",
    "updated_at": None,
}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE_URL = "/api/v1/products"

# The `client` fixture is provided by conftest.py (function-scoped, DB mocked).

# ---------------------------------------------------------------------------
# GET /products/categories
# ---------------------------------------------------------------------------

class TestCategoriesEndpoint:

    def test_returns_list_of_categories(self, client):
        with patch("app.products.service.get_categories", new_callable=AsyncMock,
                   return_value=["laptops", "phones", "tablets"]):
            resp = client.get(f"{BASE_URL}/categories")

        assert resp.status_code == 200
        assert resp.json() == ["laptops", "phones", "tablets"]

    def test_returns_500_on_service_error(self, client):
        with patch("app.products.service.get_categories",
                   new_callable=AsyncMock, side_effect=Exception("DB down")):
            resp = client.get(f"{BASE_URL}/categories")

        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /products/low-categories
# ---------------------------------------------------------------------------

class TestLowCategoriesEndpoint:

    def test_returns_list_of_low_categories(self, client):
        with patch("app.products.service.get_all_low_categories", new_callable=AsyncMock,
                   return_value=["computers", "audio"]):
            resp = client.get(f"{BASE_URL}/low-categories")

        assert resp.status_code == 200
        assert resp.json() == ["computers", "audio"]

    def test_returns_500_on_service_error(self, client):
        with patch("app.products.service.get_all_low_categories",
                   new_callable=AsyncMock, side_effect=Exception("fail")):
            resp = client.get(f"{BASE_URL}/low-categories")

        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /products/search
# ---------------------------------------------------------------------------

class TestSearchEndpoint:

    def test_short_query_returns_empty_list(self, client):
        resp = client.get(f"{BASE_URL}/search", params={"q": "a"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_valid_query_returns_results(self, client):
        with patch("app.products.service.search_products", new_callable=AsyncMock,
                   return_value=[type("SR", (), SAMPLE_SEARCH_RESULT)()]):
            # Use schema objects instead of dicts – mock with real Pydantic models
            from app.products.schemas import SearchResult
            sr = SearchResult(**SAMPLE_SEARCH_RESULT)
            with patch("app.products.service.search_products", new_callable=AsyncMock,
                       return_value=[sr]):
                resp = client.get(f"{BASE_URL}/search", params={"q": "laptop"})

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["name"] == "Laptop Pro 15"

    def test_search_with_shop_filter(self, client):
        from app.products.schemas import SearchResult
        sr = SearchResult(**SAMPLE_SEARCH_RESULT)
        with patch("app.products.service.search_products", new_callable=AsyncMock,
                   return_value=[sr]) as mock_search:
            resp = client.get(f"{BASE_URL}/search", params={"q": "laptop", "shop": "mytek"})
            mock_search.assert_called_once_with("laptop", 10, "mytek")

        assert resp.status_code == 200

    def test_returns_500_on_service_error(self, client):
        with patch("app.products.service.search_products",
                   new_callable=AsyncMock, side_effect=Exception("fail")):
            resp = client.get(f"{BASE_URL}/search", params={"q": "laptop"})

        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /products/random
# ---------------------------------------------------------------------------

class TestRandomProductsEndpoint:

    def test_returns_products(self, client):
        from app.products.schemas import Product, ShopPrice
        product = Product(**SAMPLE_PRODUCT)
        with patch("app.products.service.get_random_products", new_callable=AsyncMock,
                   return_value=[product]):
            resp = client.get(f"{BASE_URL}/random", params={"category": "laptops"})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Laptop Pro 15"

    def test_missing_category_returns_422(self, client):
        resp = client.get(f"{BASE_URL}/random")
        assert resp.status_code == 422

    def test_returns_500_on_service_error(self, client):
        with patch("app.products.service.get_random_products",
                   new_callable=AsyncMock, side_effect=Exception("DB error")):
            resp = client.get(f"{BASE_URL}/random", params={"category": "laptops"})

        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /products/by-sku/{sku}
# ---------------------------------------------------------------------------

class TestGetProductBySkuEndpoint:

    def test_found_returns_product(self, client):
        from app.products.schemas import Product
        product = Product(**SAMPLE_PRODUCT)
        with patch("app.products.service.get_product_by_sku", new_callable=AsyncMock,
                   return_value=product):
            resp = client.get(f"{BASE_URL}/by-sku/LP15")

        assert resp.status_code == 200
        assert resp.json()["name"] == "Laptop Pro 15"

    def test_not_found_returns_404(self, client):
        with patch("app.products.service.get_product_by_sku",
                   new_callable=AsyncMock, return_value=None):
            resp = client.get(f"{BASE_URL}/by-sku/UNKNOWN")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Product not found"

    def test_returns_500_on_service_error(self, client):
        with patch("app.products.service.get_product_by_sku",
                   new_callable=AsyncMock, side_effect=Exception("timeout")):
            resp = client.get(f"{BASE_URL}/by-sku/LP15")

        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /products/listing
# ---------------------------------------------------------------------------

class TestProductListingEndpoint:

    def test_basic_listing_returns_response(self, client):
        from app.products.schemas import Product, ProductListResponse
        product = Product(**SAMPLE_PRODUCT)
        listing = ProductListResponse(
            products=[product], total=1, page=1, limit=20, totalPages=1
        )
        with patch("app.products.service.get_products_listing", new_callable=AsyncMock,
                   return_value=listing):
            resp = client.get(f"{BASE_URL}/listing")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["page"] == 1
        assert len(data["products"]) == 1

    def test_listing_with_filters(self, client):
        from app.products.schemas import Product, ProductListResponse
        listing = ProductListResponse(products=[], total=0, page=1, limit=20, totalPages=0)
        with patch("app.products.service.get_products_listing", new_callable=AsyncMock,
                   return_value=listing) as mock_svc:
            resp = client.get(
                f"{BASE_URL}/listing",
                params={
                    "category": "laptops",
                    "min_price": "1000",
                    "max_price": "2000",
                    "in_stock": "true",
                    "page": "2",
                    "limit": "10",
                },
            )
            mock_svc.assert_called_once_with(
                category="laptops",
                category_type="subcategory",
                search=None,
                min_price=1000.0,
                max_price=2000.0,
                in_stock_only=True,
                page=2,
                limit=10,
            )

        assert resp.status_code == 200

    def test_page_less_than_1_returns_422(self, client):
        resp = client.get(f"{BASE_URL}/listing", params={"page": "0"})
        assert resp.status_code == 422

    def test_limit_exceeds_max_returns_422(self, client):
        resp = client.get(f"{BASE_URL}/listing", params={"limit": "101"})
        assert resp.status_code == 422

    def test_returns_500_on_service_error(self, client):
        with patch("app.products.service.get_products_listing",
                   new_callable=AsyncMock, side_effect=Exception("agg error")):
            resp = client.get(f"{BASE_URL}/listing")

        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /products/analytics/categories
# ---------------------------------------------------------------------------

class TestAnalyticsCategoriesEndpoint:

    def test_returns_list(self, client):
        with patch("app.products.service.get_analytics_categories", new_callable=AsyncMock,
                   return_value=["Audio", "Cameras", "TVs"]):
            resp = client.get(f"{BASE_URL}/analytics/categories")

        assert resp.status_code == 200
        assert resp.json() == ["Audio", "Cameras", "TVs"]

    def test_returns_500_on_error(self, client):
        with patch("app.products.service.get_analytics_categories",
                   new_callable=AsyncMock, side_effect=Exception("fail")):
            resp = client.get(f"{BASE_URL}/analytics/categories")

        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /products/analytics/by-category
# ---------------------------------------------------------------------------

class TestCategoryAnalyticsEndpoint:

    def test_found_returns_analytics(self, client):
        from app.products.schemas import CategoryAnalytics, ShopRanking
        analytics = CategoryAnalytics(
            category="laptops",
            cheapest_shop="tunisianet",
            cheapest_avg_price=1350.50,
            only_available=True,
            shop_rankings=[
                ShopRanking(
                    shop="tunisianet",
                    avg_price=1350.50,
                    min_price=1200.0,
                    max_price=1500.0,
                    product_count=42,
                )
            ],
        )
        with patch("app.products.service.get_category_analytics", new_callable=AsyncMock,
                   return_value=analytics):
            resp = client.get(f"{BASE_URL}/analytics/by-category",
                              params={"category": "laptops"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["cheapest_shop"] == "tunisianet"
        assert len(data["shop_rankings"]) == 1

    def test_not_found_returns_404(self, client):
        with patch("app.products.service.get_category_analytics",
                   new_callable=AsyncMock, return_value=None):
            resp = client.get(f"{BASE_URL}/analytics/by-category",
                              params={"category": "unknown"})

        assert resp.status_code == 404

    def test_missing_category_param_returns_422(self, client):
        resp = client.get(f"{BASE_URL}/analytics/by-category")
        assert resp.status_code == 422

    def test_returns_500_on_service_error(self, client):
        with patch("app.products.service.get_category_analytics",
                   new_callable=AsyncMock, side_effect=Exception("DB fail")):
            resp = client.get(f"{BASE_URL}/analytics/by-category",
                              params={"category": "laptops"})

        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /products/fake-promos/list
# ---------------------------------------------------------------------------

class TestFakePromosEndpoint:

    def test_returns_promo_list(self, client):
        with patch("app.products.service.get_fake_promos", new_callable=AsyncMock,
                   return_value=[SAMPLE_FAKE_PROMO]):
            resp = client.get(f"{BASE_URL}/fake-promos/list")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["title"] == "Fake Deal TV"

    def test_limit_param_is_forwarded(self, client):
        with patch("app.products.service.get_fake_promos",
                   new_callable=AsyncMock, return_value=[]) as mock_svc:
            client.get(f"{BASE_URL}/fake-promos/list", params={"limit": "50"})
            mock_svc.assert_called_once_with(limit=50)

    def test_returns_500_on_service_error(self, client):
        with patch("app.products.service.get_fake_promos",
                   new_callable=AsyncMock, side_effect=Exception("fail")):
            resp = client.get(f"{BASE_URL}/fake-promos/list")

        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /products/{product_id}  (must be last - catch-all route)
# ---------------------------------------------------------------------------

class TestGetProductByIdEndpoint:

    def test_found_returns_product(self, client):
        from app.products.schemas import Product
        product = Product(**SAMPLE_PRODUCT)
        with patch("app.products.service.get_product_by_id", new_callable=AsyncMock,
                   return_value=product):
            resp = client.get(f"{BASE_URL}/64abc123")

        assert resp.status_code == 200
        assert resp.json()["name"] == "Laptop Pro 15"

    def test_not_found_returns_404(self, client):
        with patch("app.products.service.get_product_by_id",
                   new_callable=AsyncMock, return_value=None):
            resp = client.get(f"{BASE_URL}/nonexistent-id")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Product not found"

    def test_returns_500_on_service_error(self, client):
        with patch("app.products.service.get_product_by_id",
                   new_callable=AsyncMock, side_effect=Exception("err")):
            resp = client.get(f"{BASE_URL}/64abc123")

        assert resp.status_code == 500
