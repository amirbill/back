"""
Unit tests for app/products/service.py

Tests cover:
  - Pure parsing helpers (parse_product, parse_single_shop_product)
  - Async DB-dependent functions (get_categories, get_all_low_categories,
    get_random_products, get_product_by_sku, search_products,
    get_analytics_categories, get_category_analytics)

All DB calls are mocked so no real MongoDB instance is required.
Run with:  pytest tests/test_products_service.py -v
"""
import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/test")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously (no pytest-asyncio needed)."""
    return asyncio.get_event_loop().run_until_complete(coro)


class AsyncIter:
    """Minimal async iterator that wraps a plain list."""

    def __init__(self, items):
        self._iter = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _mock_db(collection_mock):
    """Return a mock db whose client["Retails"][*] resolves to collection_mock."""
    mock_db = MagicMock()
    mock_client = MagicMock()
    mock_db.client = mock_client
    mock_client.__getitem__.return_value.__getitem__.return_value = collection_mock
    return mock_db


# ---------------------------------------------------------------------------
# Sample raw documents
# ---------------------------------------------------------------------------

SAMPLE_MERGED_DOC = {
    "_id": "64abc123",
    "title": "Laptop Pro 15",
    "sku": "LP15",
    "subcategory": "laptops",
    "low_category": "computers",
    "shops": {
        "mytek": {
            "price": "1500",
            "old_price": "1800",
            "available": True,
            "url": "https://mytek.tn/laptop",
            "images": ["https://mytek.tn/img/laptop.jpg"],
            "brand": "brand_a",
        },
        "tunisianet": {
            "price": "1400",
            "old_price": None,
            "available": False,
            "url": "https://tunisianet.tn/laptop",
            "images": ["https://tunisianet.tn/img/laptop.jpg"],
            "brand": "brand_b",
        },
    },
}

SAMPLE_SINGLE_SHOP_DOC = {
    "_id": "64xyz789",
    "title": "Smartphone X12",
    "sku": "SX12",
    "price": "500",
    "old_price": "600",
    "available": True,
    "images": ["https://mytek.tn/img/phone.jpg"],
    "brand": "techbrand",
    "subcategory": "smartphones",
    "overview": "A great smartphone",
    "specifications": {"RAM": "8GB"},
}


# ---------------------------------------------------------------------------
# 1. parse_product (pure function)
# ---------------------------------------------------------------------------

class TestParseProduct:
    from app.products.service import parse_product  # imported at class level avoids re-import

    def test_basic_fields(self):
        from app.products.service import parse_product
        product = parse_product(SAMPLE_MERGED_DOC)

        assert product.name == "Laptop Pro 15"
        assert product.category == "laptops"
        assert product.inStock is True  # mytek is available

    def test_best_price_is_lowest(self):
        from app.products.service import parse_product
        product = parse_product(SAMPLE_MERGED_DOC)
        # tunisianet price 1400 < mytek price 1500
        assert product.bestPrice == 1400.0

    def test_shop_prices_sorted_ascending(self):
        from app.products.service import parse_product
        product = parse_product(SAMPLE_MERGED_DOC)
        prices = [sp.price for sp in product.shopPrices]
        assert prices == sorted(prices)

    def test_original_price_from_old_price(self):
        from app.products.service import parse_product
        product = parse_product(SAMPLE_MERGED_DOC)
        # Only mytek has old_price=1800
        assert product.originalPrice == 1800.0

    def test_brand_is_uppercased(self):
        from app.products.service import parse_product
        product = parse_product(SAMPLE_MERGED_DOC)
        assert product.brand == "BRAND_A"

    def test_skips_livraison_image(self):
        from app.products.service import parse_product
        doc = {
            "_id": "abc",
            "title": "Widget",
            "shops": {
                "spacenet": {
                    "price": "100",
                    "available": True,
                    "images": [
                        "https://spacenet.tn/livraison-gratuite.jpg",
                        "https://spacenet.tn/product.jpg",
                    ],
                }
            },
        }
        product = parse_product(doc)
        assert "livraison-gratuite" not in product.image
        assert product.image == "https://spacenet.tn/product.jpg"

    def test_placeholder_when_only_livraison_image(self):
        from app.products.service import parse_product
        doc = {
            "_id": "abc",
            "title": "Widget",
            "shops": {
                "spacenet": {
                    "price": "100",
                    "available": True,
                    "images": ["https://spacenet.tn/livraison-gratuite.jpg"],
                }
            },
        }
        product = parse_product(doc)
        assert product.image == "/placeholder.svg"

    def test_include_specs_merges_specifications(self):
        from app.products.service import parse_product
        doc = {
            "_id": "abc",
            "title": "Monitor",
            "shops": {
                "mytek": {
                    "price": "300",
                    "available": True,
                    "images": [],
                    "specifications": {"Resolution": "4K", "Size": "27in"},
                }
            },
        }
        product = parse_product(doc, include_specs=True)
        assert product.specifications == {"Resolution": "4K", "Size": "27in"}

    def test_in_stock_false_when_all_unavailable(self):
        from app.products.service import parse_product
        doc = {
            "_id": "abc",
            "title": "OOS Product",
            "shops": {
                "mytek": {"price": "200", "available": False, "images": []},
            },
        }
        product = parse_product(doc)
        assert product.inStock is False

    def test_empty_shops_returns_best_price_zero(self):
        from app.products.service import parse_product
        doc = {"_id": "abc", "title": "No shops", "shops": {}}
        product = parse_product(doc)
        assert product.bestPrice == 0.0
        assert product.shopPrices == []


# ---------------------------------------------------------------------------
# 2. parse_single_shop_product (pure function)
# ---------------------------------------------------------------------------

class TestParseSingleShopProduct:

    def test_basic_fields(self):
        from app.products.service import parse_single_shop_product
        product = parse_single_shop_product(SAMPLE_SINGLE_SHOP_DOC, "mytek")

        assert product.name == "Smartphone X12"
        assert product.bestPrice == 500.0
        assert product.originalPrice == 600.0
        assert product.inStock is True
        assert product.brand == "TECHBRAND"

    def test_shop_price_entry(self):
        from app.products.service import parse_single_shop_product
        product = parse_single_shop_product(SAMPLE_SINGLE_SHOP_DOC, "mytek")
        assert len(product.shopPrices) == 1
        assert product.shopPrices[0].shop == "Mytek"
        assert product.shopPrices[0].price == 500.0

    def test_image_selection(self):
        from app.products.service import parse_single_shop_product
        product = parse_single_shop_product(SAMPLE_SINGLE_SHOP_DOC, "mytek")
        assert product.image == "https://mytek.tn/img/phone.jpg"

    def test_skips_livraison_image(self):
        from app.products.service import parse_single_shop_product
        doc = {
            **SAMPLE_SINGLE_SHOP_DOC,
            "images": [
                "https://spacenet.tn/livraison-gratuite.jpg",
                "https://spacenet.tn/real.jpg",
            ],
        }
        product = parse_single_shop_product(doc, "spacenet")
        assert product.image == "https://spacenet.tn/real.jpg"

    def test_no_old_price(self):
        from app.products.service import parse_single_shop_product
        doc = {**SAMPLE_SINGLE_SHOP_DOC, "old_price": None}
        product = parse_single_shop_product(doc, "mytek")
        assert product.originalPrice is None


# ---------------------------------------------------------------------------
# 3. get_categories (async)
# ---------------------------------------------------------------------------

class TestGetCategories:

    def test_returns_sorted_categories(self):
        from app.products import service

        mock_coll = AsyncMock()
        mock_coll.distinct = AsyncMock(return_value=["Televisions", "Laptops", "Phones"])

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            result = _run(service.get_categories())

        assert result == ["Laptops", "Phones", "Televisions"]

    def test_filters_empty_strings(self):
        from app.products import service

        mock_coll = AsyncMock()
        mock_coll.distinct = AsyncMock(return_value=["Laptops", "", None, "Phones"])

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            result = _run(service.get_categories())

        assert "" not in result
        assert None not in result

    def test_returns_empty_list_on_error(self):
        from app.products import service

        mock_coll = AsyncMock()
        mock_coll.distinct = AsyncMock(side_effect=Exception("DB error"))

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            result = _run(service.get_categories())

        assert result == []


# ---------------------------------------------------------------------------
# 4. get_all_low_categories (async)
# ---------------------------------------------------------------------------

class TestGetAllLowCategories:

    def test_returns_sorted_low_categories(self):
        from app.products import service

        mock_coll = AsyncMock()
        mock_coll.distinct = AsyncMock(return_value=["computers", "audio", "cameras"])

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            result = _run(service.get_all_low_categories())

        assert result == ["audio", "cameras", "computers"]

    def test_returns_empty_list_on_error(self):
        from app.products import service

        mock_coll = AsyncMock()
        mock_coll.distinct = AsyncMock(side_effect=RuntimeError("timeout"))

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            result = _run(service.get_all_low_categories())

        assert result == []


# ---------------------------------------------------------------------------
# 5. get_random_products (async)
# ---------------------------------------------------------------------------

class TestGetRandomProducts:

    def test_returns_products_from_aggregate(self):
        from app.products import service

        mock_coll = MagicMock()
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[SAMPLE_MERGED_DOC])
        mock_coll.aggregate.return_value = mock_cursor

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            products = _run(service.get_random_products("laptops", "subcategory", 5))

        assert len(products) == 1
        assert products[0].name == "Laptop Pro 15"

    def test_limit_is_capped_at_10(self):
        from app.products import service

        mock_coll = MagicMock()
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_coll.aggregate.return_value = mock_cursor

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            _run(service.get_random_products("laptops", "subcategory", 50))

        # Check that $sample size was capped at 10
        call_args = mock_coll.aggregate.call_args[0][0]
        sample_stage = next(s for s in call_args if "$sample" in s)
        assert sample_stage["$sample"]["size"] == 10

    def test_fallback_pipeline_used_when_no_results(self):
        from app.products import service

        mock_coll = MagicMock()
        empty_cursor = AsyncMock()
        empty_cursor.to_list = AsyncMock(return_value=[])
        fallback_cursor = AsyncMock()
        fallback_cursor.to_list = AsyncMock(return_value=[SAMPLE_MERGED_DOC])

        mock_coll.aggregate.side_effect = [empty_cursor, fallback_cursor]

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            products = _run(service.get_random_products("some-category", "subcategory", 5))

        assert mock_coll.aggregate.call_count == 2
        assert len(products) == 1


# ---------------------------------------------------------------------------
# 6. get_product_by_sku (async)
# ---------------------------------------------------------------------------

class TestGetProductBySku:

    def test_found_in_merged_products(self):
        from app.products import service

        mock_coll = AsyncMock()
        mock_coll.find_one = AsyncMock(return_value=SAMPLE_MERGED_DOC)

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            product = _run(service.get_product_by_sku("LP15"))

        assert product is not None
        assert product.name == "Laptop Pro 15"

    def test_returns_none_when_not_found(self):
        from app.products import service

        mock_coll = AsyncMock()
        mock_coll.find_one = AsyncMock(return_value=None)

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            product = _run(service.get_product_by_sku("NONEXISTENT"))

        assert product is None


# ---------------------------------------------------------------------------
# 7. search_products (async)
# ---------------------------------------------------------------------------

class TestSearchProducts:

    def test_returns_search_results(self):
        from app.products import service

        mock_coll = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.limit.return_value = AsyncIter([SAMPLE_MERGED_DOC])
        mock_coll.find.return_value = mock_cursor

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            results = _run(service.search_products("Laptop", limit=5))

        assert len(results) >= 1
        assert results[0].name == "Laptop Pro 15"

    def test_deduplicates_by_sku(self):
        from app.products import service

        # Two docs with the same SKU should produce one result
        doc2 = {**SAMPLE_MERGED_DOC, "sku": "LP15"}
        mock_coll = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.limit.return_value = AsyncIter([SAMPLE_MERGED_DOC, doc2])
        mock_coll.find.return_value = mock_cursor

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            results = _run(service.search_products("Laptop", limit=10))

        ids = [r.id for r in results]
        assert len(ids) == len(set(ids))

    def test_respects_limit(self):
        from app.products import service

        docs = [
            {**SAMPLE_MERGED_DOC, "_id": f"id{i}", "sku": f"SKU{i}"}
            for i in range(20)
        ]
        mock_coll = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.limit.return_value = AsyncIter(docs[:5])
        mock_coll.find.return_value = mock_cursor

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            results = _run(service.search_products("Laptop", limit=5))

        assert len(results) <= 5


# ---------------------------------------------------------------------------
# 8. get_analytics_categories (async)
# ---------------------------------------------------------------------------

class TestGetAnalyticsCategories:

    def test_returns_sorted_categories(self):
        from app.products import service

        mock_coll = AsyncMock()
        mock_coll.distinct = AsyncMock(return_value=["TVs", "Audio", "Cameras"])

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            result = _run(service.get_analytics_categories())

        assert result == ["Audio", "Cameras", "TVs"]

    def test_returns_empty_list_on_error(self):
        from app.products import service

        mock_coll = AsyncMock()
        mock_coll.distinct = AsyncMock(side_effect=Exception("connection error"))

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            result = _run(service.get_analytics_categories())

        assert result == []


# ---------------------------------------------------------------------------
# 9. get_category_analytics (async)
# ---------------------------------------------------------------------------

SAMPLE_ANALYTICS_DOC = {
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
        },
        {
            "shop": "mytek",
            "avg_price": 1420.0,
            "min_price": 1250.0,
            "max_price": 1600.0,
            "product_count": 38,
        },
    ],
}


class TestGetCategoryAnalytics:

    def test_found_returns_analytics(self):
        from app.products import service

        mock_coll = AsyncMock()
        mock_coll.find_one = AsyncMock(return_value=SAMPLE_ANALYTICS_DOC)

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            result = _run(service.get_category_analytics("laptops"))

        assert result is not None
        assert result.category == "laptops"
        assert result.cheapest_shop == "tunisianet"
        assert len(result.shop_rankings) == 2
        assert result.shop_rankings[0].shop == "tunisianet"

    def test_not_found_returns_none(self):
        from app.products import service

        mock_coll = AsyncMock()
        mock_coll.find_one = AsyncMock(return_value=None)

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            result = _run(service.get_category_analytics("unknown-category"))

        assert result is None

    def test_returns_none_on_db_error(self):
        from app.products import service

        mock_coll = AsyncMock()
        mock_coll.find_one = AsyncMock(side_effect=Exception("DB error"))

        with patch.object(service, "get_database", return_value=_mock_db(mock_coll)):
            result = _run(service.get_category_analytics("laptops"))

        assert result is None
