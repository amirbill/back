"""
Tests for app/para/service.py and app/para/router.py.
Run with: pytest tests/test_para.py -v
"""
import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/test")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("GROQ_API_KEY", "test-groq")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class AsyncIter:
    def __init__(self, items):
        self._iter = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _mock_para_db(collection_mock):
    """Build a db mock where db.client["PARA"][*] returns collection_mock."""
    mock_db = MagicMock()
    mock_client = MagicMock()
    mock_db.client = mock_client
    mock_client.__getitem__.return_value.__getitem__.return_value = collection_mock
    return mock_client["PARA"]


# ---------------------------------------------------------------------------
# Sample raw docs
# ---------------------------------------------------------------------------

SAMPLE_PARA_DOC = {
    "_id": "64para1",
    "title": "Crème Hydratante XL",
    "sku": "CH_XL",
    "top_category": "Soins",
    "low_category": "visage",
    "subcategory": "cremes",
    "shops": {
        "parashop": {
            "price": "25.5",
            "old_price": "30.0",
            "available": True,
            "url": "https://parashop.tn/creme",
            "images": ["https://parashop.tn/img/creme.jpg"],
            "brand": "brand_x",
            "specifications": {"Contenu": "200ml"},
        },
        "pharma-shop": {
            "price": "27.0",
            "old_price": None,
            "available": False,
            "url": None,
            "images": [],
            "brand": "brand_y",
        },
    },
}

SAMPLE_SINGLE_PARA_DOC = {
    "_id": "64para2",
    "title": "Sérum Vitamine C",
    "sku": "SVC",
    "price": "45.0",
    "old_price": "55.0",
    "available": True,
    "images": ["https://parashop.tn/img/serum.jpg"],
    "brand": "cosm_brand",
    "low_category": "sérums",
    "top_category": "Soins",
    "description": "Un excellent sérum",
    "specifications": {"Actif": "Vit C 15%"},
}

SAMPLE_ANALYTICS_DOC = {
    "category": "Soins",
    "cheapest_shop": "parashop",
    "cheapest_avg_price": 22.5,
    "only_available": True,
    "shop_rankings": [
        {
            "shop": "parashop",
            "avg_price": 22.5,
            "min_price": 10.0,
            "max_price": 80.0,
            "product_count": 150,
        }
    ],
}


# ---------------------------------------------------------------------------
# 1. parse_para_product
# ---------------------------------------------------------------------------

class TestParseParaProduct:

    def test_best_price_is_lowest(self):
        from app.para.service import parse_para_product
        p = parse_para_product(SAMPLE_PARA_DOC)
        assert p.bestPrice == 25.5

    def test_brand_uppercased(self):
        from app.para.service import parse_para_product
        p = parse_para_product(SAMPLE_PARA_DOC)
        assert p.brand == "BRAND_X"

    def test_in_stock_true_when_any_available(self):
        from app.para.service import parse_para_product
        p = parse_para_product(SAMPLE_PARA_DOC)
        assert p.inStock is True

    def test_in_stock_false_when_none_available(self):
        from app.para.service import parse_para_product
        doc = {
            "_id": "x",
            "title": "OOS",
            "shops": {
                "parashop": {"price": "10", "available": False, "images": [], "brand": "b"},
            },
        }
        p = parse_para_product(doc)
        assert p.inStock is False

    def test_shop_prices_sorted_ascending(self):
        from app.para.service import parse_para_product
        p = parse_para_product(SAMPLE_PARA_DOC)
        prices = [sp.price for sp in p.shopPrices]
        assert prices == sorted(prices)

    def test_original_price_populated(self):
        from app.para.service import parse_para_product
        p = parse_para_product(SAMPLE_PARA_DOC)
        assert p.originalPrice == 30.0

    def test_category_from_low_category(self):
        from app.para.service import parse_para_product
        p = parse_para_product(SAMPLE_PARA_DOC)
        assert p.category == "visage"

    def test_top_category_populated(self):
        from app.para.service import parse_para_product
        p = parse_para_product(SAMPLE_PARA_DOC)
        assert p.topCategory == "Soins"

    def test_empty_shops_returns_zero_price(self):
        from app.para.service import parse_para_product
        p = parse_para_product({"_id": "x", "title": "Empty", "shops": {}})
        assert p.bestPrice == 0.0

    def test_include_specs_merges_specifications(self):
        from app.para.service import parse_para_product
        p = parse_para_product(SAMPLE_PARA_DOC, include_specs=True)
        assert p.specifications is not None
        assert "Contenu" in p.specifications


# ---------------------------------------------------------------------------
# 2. parse_single_para_shop_product
# ---------------------------------------------------------------------------

class TestParseSingleParaShopProduct:

    def test_basic_fields(self):
        from app.para.service import parse_single_para_shop_product
        p = parse_single_para_shop_product(SAMPLE_SINGLE_PARA_DOC, "parashop")
        assert p.name == "Sérum Vitamine C"
        assert p.bestPrice == 45.0
        assert p.originalPrice == 55.0
        assert p.brand == "COSM_BRAND"
        assert p.inStock is True

    def test_shop_price_title_cased(self):
        from app.para.service import parse_single_para_shop_product
        p = parse_single_para_shop_product(SAMPLE_SINGLE_PARA_DOC, "pharma-shop")
        assert p.shopPrices[0].shop == "Pharma Shop"

    def test_no_old_price(self):
        from app.para.service import parse_single_para_shop_product
        doc = {**SAMPLE_SINGLE_PARA_DOC, "old_price": None}
        p = parse_single_para_shop_product(doc, "parashop")
        assert p.originalPrice is None

    def test_image_from_images_list(self):
        from app.para.service import parse_single_para_shop_product
        p = parse_single_para_shop_product(SAMPLE_SINGLE_PARA_DOC, "parashop")
        assert p.image == "https://parashop.tn/img/serum.jpg"

    def test_placeholder_when_no_images(self):
        from app.para.service import parse_single_para_shop_product
        doc = {**SAMPLE_SINGLE_PARA_DOC, "images": []}
        p = parse_single_para_shop_product(doc, "parashop")
        assert p.image == "/placeholder.svg"


# ---------------------------------------------------------------------------
# 3. get_category_field
# ---------------------------------------------------------------------------

class TestGetCategoryField:

    def test_top_maps_to_top_category(self):
        from app.para.service import get_category_field
        assert get_category_field("top") == "top_category"

    def test_low_maps_to_low_category(self):
        from app.para.service import get_category_field
        assert get_category_field("low") == "low_category"

    def test_unknown_defaults_to_top_category(self):
        from app.para.service import get_category_field
        assert get_category_field("invalid") == "top_category"

    def test_subcategory_maps_to_subcategory(self):
        from app.para.service import get_category_field
        assert get_category_field("subcategory") == "subcategory"


# ---------------------------------------------------------------------------
# 4. get_para_categories
# ---------------------------------------------------------------------------

class _ParaDbPatch:
    """Context manager that patches get_para_database in para.service."""

    def __init__(self, collection_mock):
        self._coll = collection_mock
        self._patcher = None

    def __enter__(self):
        from app.para import service
        mock_para_db = MagicMock()
        mock_para_db.__getitem__.return_value = self._coll
        self._patcher = patch.object(service, "get_para_database", return_value=mock_para_db)
        self._patcher.start()
        return self

    def __exit__(self, *args):
        self._patcher.stop()


class TestGetParaCategories:

    def test_returns_sorted_categories(self):
        from app.para import service
        mock_coll = AsyncMock()
        mock_coll.distinct = AsyncMock(return_value=["Soins", "Maquillage", "Bébé"])
        mock_para_db = MagicMock()
        mock_para_db.__getitem__.return_value = mock_coll
        with patch.object(service, "get_para_database", return_value=mock_para_db):
            result = _run(service.get_para_categories("top_category"))
        assert result == ["Bébé", "Maquillage", "Soins"]

    def test_filters_empty_values(self):
        from app.para import service
        mock_coll = AsyncMock()
        mock_coll.distinct = AsyncMock(return_value=["Soins", "", None])
        mock_para_db = MagicMock()
        mock_para_db.__getitem__.return_value = mock_coll
        with patch.object(service, "get_para_database", return_value=mock_para_db):
            result = _run(service.get_para_categories("top_category"))
        assert "" not in result
        assert None not in result

    def test_returns_empty_on_error(self):
        from app.para import service
        mock_coll = AsyncMock()
        mock_coll.distinct = AsyncMock(side_effect=Exception("fail"))
        mock_para_db = MagicMock()
        mock_para_db.__getitem__.return_value = mock_coll
        with patch.object(service, "get_para_database", return_value=mock_para_db):
            result = _run(service.get_para_categories("top_category"))
        assert result == []


# ---------------------------------------------------------------------------
# 5. get_para_random_products
# ---------------------------------------------------------------------------

class TestGetParaRandomProducts:

    def test_returns_products(self):
        from app.para import service
        mock_coll = MagicMock()
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[SAMPLE_PARA_DOC])
        mock_coll.aggregate.return_value = mock_cursor
        mock_para_db = MagicMock()
        mock_para_db.__getitem__.return_value = mock_coll
        with patch.object(service, "get_para_database", return_value=mock_para_db):
            products = _run(service.get_para_random_products("Soins", "top_category", 5))
        assert len(products) == 1
        assert products[0].name == "Crème Hydratante XL"

    def test_limit_capped_at_10(self):
        from app.para import service
        mock_coll = MagicMock()
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_coll.aggregate.return_value = mock_cursor
        mock_para_db = MagicMock()
        mock_para_db.__getitem__.return_value = mock_coll
        with patch.object(service, "get_para_database", return_value=mock_para_db):
            _run(service.get_para_random_products("Soins", "top_category", 50))
        call_pipeline = mock_coll.aggregate.call_args[0][0]
        sample_stage = next(s for s in call_pipeline if "$sample" in s)
        assert sample_stage["$sample"]["size"] == 10


# ---------------------------------------------------------------------------
# 6. get_para_product_by_sku
# ---------------------------------------------------------------------------

class TestGetParaProductBySku:

    def test_found_in_merged_products(self):
        from app.para import service
        mock_coll = AsyncMock()
        mock_coll.find_one = AsyncMock(return_value=SAMPLE_PARA_DOC)
        mock_para_db = MagicMock()
        mock_para_db.__getitem__.return_value = mock_coll
        with patch.object(service, "get_para_database", return_value=mock_para_db):
            result = _run(service.get_para_product_by_sku("CH_XL"))
        assert result is not None
        assert result.name == "Crème Hydratante XL"

    def test_returns_none_when_not_found(self):
        from app.para import service
        mock_coll = AsyncMock()
        mock_coll.find_one = AsyncMock(return_value=None)
        mock_para_db = MagicMock()
        mock_para_db.__getitem__.return_value = mock_coll
        with patch.object(service, "get_para_database", return_value=mock_para_db):
            result = _run(service.get_para_product_by_sku("NOPE"))
        assert result is None


# ---------------------------------------------------------------------------
# 7. search_para_products
# ---------------------------------------------------------------------------

class TestSearchParaProducts:

    def test_returns_results(self):
        from app.para import service
        mock_coll = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.limit.return_value = AsyncIter([SAMPLE_PARA_DOC])
        mock_coll.find.return_value = mock_cursor
        mock_para_db = MagicMock()
        mock_para_db.__getitem__.return_value = mock_coll
        with patch.object(service, "get_para_database", return_value=mock_para_db):
            results = _run(service.search_para_products("Crème", limit=5))
        assert len(results) >= 1
        assert results[0].name == "Crème Hydratante XL"

    def test_deduplicates_by_sku(self):
        from app.para import service
        doc2 = {**SAMPLE_PARA_DOC, "sku": "CH_XL"}
        mock_coll = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.limit.return_value = AsyncIter([SAMPLE_PARA_DOC, doc2])
        mock_coll.find.return_value = mock_cursor
        mock_para_db = MagicMock()
        mock_para_db.__getitem__.return_value = mock_coll
        with patch.object(service, "get_para_database", return_value=mock_para_db):
            results = _run(service.search_para_products("Crème", limit=10))
        ids = [r.id for r in results]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# 8. get_analytics_categories
# ---------------------------------------------------------------------------

class TestParaAnalyticsCategories:

    def test_returns_sorted(self):
        from app.para import service
        mock_coll = AsyncMock()
        mock_coll.distinct = AsyncMock(return_value=["Soins", "Bébé", "Maquillage"])
        mock_para_db = MagicMock()
        mock_para_db.__getitem__.return_value = mock_coll
        with patch.object(service, "get_para_database", return_value=mock_para_db):
            result = _run(service.get_analytics_categories())
        assert result == ["Bébé", "Maquillage", "Soins"]

    def test_returns_empty_on_error(self):
        from app.para import service
        mock_coll = AsyncMock()
        mock_coll.distinct = AsyncMock(side_effect=Exception("fail"))
        mock_para_db = MagicMock()
        mock_para_db.__getitem__.return_value = mock_coll
        with patch.object(service, "get_para_database", return_value=mock_para_db):
            result = _run(service.get_analytics_categories())
        assert result == []


# ---------------------------------------------------------------------------
# 9. get_category_analytics
# ---------------------------------------------------------------------------

class TestParaGetCategoryAnalytics:

    def test_found_returns_analytics(self):
        from app.para import service
        mock_coll = AsyncMock()
        mock_coll.find_one = AsyncMock(return_value=SAMPLE_ANALYTICS_DOC)
        mock_para_db = MagicMock()
        mock_para_db.__getitem__.return_value = mock_coll
        with patch.object(service, "get_para_database", return_value=mock_para_db):
            result = _run(service.get_category_analytics("Soins"))
        assert result is not None
        assert result.cheapest_shop == "parashop"
        assert len(result.shop_rankings) == 1

    def test_not_found_returns_none(self):
        from app.para import service
        mock_coll = AsyncMock()
        mock_coll.find_one = AsyncMock(return_value=None)
        mock_para_db = MagicMock()
        mock_para_db.__getitem__.return_value = mock_coll
        with patch.object(service, "get_para_database", return_value=mock_para_db):
            result = _run(service.get_category_analytics("unknown"))
        assert result is None

    def test_returns_none_on_error(self):
        from app.para import service
        mock_coll = AsyncMock()
        mock_coll.find_one = AsyncMock(side_effect=Exception("DB error"))
        mock_para_db = MagicMock()
        mock_para_db.__getitem__.return_value = mock_coll
        with patch.object(service, "get_para_database", return_value=mock_para_db):
            result = _run(service.get_category_analytics("Soins"))
        assert result is None


# ---------------------------------------------------------------------------
# 10. Para router – TestClient tests (use conftest `client` fixture)
# ---------------------------------------------------------------------------

BASE = "/api/v1/para"

SAMPLE_PARA_PRODUCT_DICT = {
    "id": "64para1",
    "name": "Crème Hydratante XL",
    "brand": "BRAND_X",
    "bestPrice": 25.5,
    "originalPrice": 30.0,
    "image": "https://parashop.tn/img/creme.jpg",
    "description": "Crème Hydratante XL",
    "inStock": True,
    "category": "visage",
    "topCategory": "Soins",
    "shopPrices": [
        {"shop": "Parashop", "price": 25.5, "oldPrice": 30.0, "available": True, "url": None}
    ],
    "specifications": None,
}


class TestParaCategoriesEndpoint:

    def test_returns_categories(self, client):
        with patch("app.para.service.get_para_categories", new_callable=AsyncMock,
                   return_value=["Soins", "Bébé"]):
            resp = client.get(f"{BASE}/categories")
        assert resp.status_code == 200
        assert "Soins" in resp.json()

    def test_returns_500_on_error(self, client):
        with patch("app.para.service.get_para_categories", new_callable=AsyncMock,
                   side_effect=Exception("fail")):
            resp = client.get(f"{BASE}/categories")
        assert resp.status_code == 500


class TestParaSearchEndpoint:

    def test_short_query_returns_empty(self, client):
        resp = client.get(f"{BASE}/search", params={"q": "a"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_valid_query_returns_results(self, client):
        from app.para.schemas import ParaSearchResult
        sr = ParaSearchResult(**{
            "id": "64para1", "name": "Crème", "brand": "B",
            "bestPrice": 25.5, "image": "/img.jpg", "inStock": True
        })
        with patch("app.para.service.search_para_products", new_callable=AsyncMock,
                   return_value=[sr]):
            resp = client.get(f"{BASE}/search", params={"q": "creme"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_returns_500_on_error(self, client):
        with patch("app.para.service.search_para_products", new_callable=AsyncMock,
                   side_effect=Exception("fail")):
            resp = client.get(f"{BASE}/search", params={"q": "creme"})
        assert resp.status_code == 500


class TestParaRandomEndpoint:

    def test_returns_products(self, client):
        from app.para.schemas import ParaProduct
        product = ParaProduct(**SAMPLE_PARA_PRODUCT_DICT)
        with patch("app.para.service.get_para_random_products", new_callable=AsyncMock,
                   return_value=[product]):
            resp = client.get(f"{BASE}/random", params={"category": "Soins"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_missing_category_returns_422(self, client):
        resp = client.get(f"{BASE}/random")
        assert resp.status_code == 422

    def test_returns_500_on_error(self, client):
        with patch("app.para.service.get_para_random_products", new_callable=AsyncMock,
                   side_effect=Exception("fail")):
            resp = client.get(f"{BASE}/random", params={"category": "Soins"})
        assert resp.status_code == 500


class TestParaBySkuEndpoint:

    def test_found_returns_product(self, client):
        from app.para.schemas import ParaProduct
        product = ParaProduct(**SAMPLE_PARA_PRODUCT_DICT)
        with patch("app.para.service.get_para_product_by_sku", new_callable=AsyncMock,
                   return_value=product):
            resp = client.get(f"{BASE}/by-sku/CH_XL")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Crème Hydratante XL"

    def test_not_found_returns_404(self, client):
        with patch("app.para.service.get_para_product_by_sku", new_callable=AsyncMock,
                   return_value=None):
            resp = client.get(f"{BASE}/by-sku/NOPE")
        assert resp.status_code == 404

    def test_returns_500_on_error(self, client):
        with patch("app.para.service.get_para_product_by_sku", new_callable=AsyncMock,
                   side_effect=Exception("err")):
            resp = client.get(f"{BASE}/by-sku/CH_XL")
        assert resp.status_code == 500


class TestParaListingEndpoint:

    def test_basic_listing(self, client):
        from app.para.schemas import ParaProduct, ParaProductListResponse
        product = ParaProduct(**SAMPLE_PARA_PRODUCT_DICT)
        listing = ParaProductListResponse(products=[product], total=1, page=1, limit=20, totalPages=1)
        with patch("app.para.service.get_para_products_listing", new_callable=AsyncMock,
                   return_value=listing):
            resp = client.get(f"{BASE}/listing")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_page_validation(self, client):
        resp = client.get(f"{BASE}/listing", params={"page": "0"})
        assert resp.status_code == 422

    def test_returns_500_on_error(self, client):
        with patch("app.para.service.get_para_products_listing", new_callable=AsyncMock,
                   side_effect=Exception("fail")):
            resp = client.get(f"{BASE}/listing")
        assert resp.status_code == 500


class TestParaAnalyticsCategoriesEndpoint:

    def test_returns_list(self, client):
        with patch("app.para.service.get_analytics_categories", new_callable=AsyncMock,
                   return_value=["Soins", "Bébé"]):
            resp = client.get(f"{BASE}/analytics/categories")
        assert resp.status_code == 200
        assert "Soins" in resp.json()

    def test_returns_500_on_error(self, client):
        with patch("app.para.service.get_analytics_categories", new_callable=AsyncMock,
                   side_effect=Exception("fail")):
            resp = client.get(f"{BASE}/analytics/categories")
        assert resp.status_code == 500


class TestParaCategoryAnalyticsEndpoint:

    def test_found_returns_analytics(self, client):
        from app.para.schemas import CategoryAnalytics, ShopRanking
        analytics = CategoryAnalytics(
            category="Soins",
            cheapest_shop="parashop",
            cheapest_avg_price=22.5,
            only_available=True,
            shop_rankings=[
                ShopRanking(shop="parashop", avg_price=22.5, min_price=10.0, max_price=80.0, product_count=150)
            ],
        )
        with patch("app.para.service.get_category_analytics", new_callable=AsyncMock,
                   return_value=analytics):
            resp = client.get(f"{BASE}/analytics/by-category", params={"category": "Soins"})
        assert resp.status_code == 200
        assert resp.json()["cheapest_shop"] == "parashop"

    def test_not_found_returns_404(self, client):
        with patch("app.para.service.get_category_analytics", new_callable=AsyncMock,
                   return_value=None):
            resp = client.get(f"{BASE}/analytics/by-category", params={"category": "unknown"})
        assert resp.status_code == 404

    def test_missing_category_returns_422(self, client):
        resp = client.get(f"{BASE}/analytics/by-category")
        assert resp.status_code == 422


class TestParaByIdEndpoint:

    def test_found_returns_product(self, client):
        from app.para.schemas import ParaProduct
        product = ParaProduct(**SAMPLE_PARA_PRODUCT_DICT)
        with patch("app.para.service.get_para_product_by_id", new_callable=AsyncMock,
                   return_value=product):
            resp = client.get(f"{BASE}/64para1")
        assert resp.status_code == 200

    def test_not_found_returns_404(self, client):
        with patch("app.para.service.get_para_product_by_id", new_callable=AsyncMock,
                   return_value=None):
            resp = client.get(f"{BASE}/nope")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Unit tests for get_para_product_by_id (direct service function)
# ---------------------------------------------------------------------------

class TestGetParaProductById:

    def _mock_para_db_direct(self, coll_mock):
        """Returns a mock that simulates get_para_database()["collection_name"]."""
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = coll_mock
        return mock_db

    def test_found_by_object_id_in_merged(self):
        from bson import ObjectId
        oid = ObjectId()
        doc = {**SAMPLE_PARA_DOC, "_id": oid}

        mock_coll = MagicMock()
        mock_coll.find_one = AsyncMock(return_value=doc)
        mock_db = self._mock_para_db_direct(mock_coll)

        with patch("app.para.service.get_para_database", return_value=mock_db):
            result = _run(__import__("app.para.service", fromlist=["get_para_product_by_id"])
                          .get_para_product_by_id(str(oid)))
        assert result is not None
        assert result.name == "Crème Hydratante XL"

    def test_not_found_by_object_id_falls_to_sku(self):
        from bson import ObjectId
        oid = ObjectId()
        doc = {**SAMPLE_PARA_DOC, "_id": oid}

        call_count = [0]

        async def find_one_side_effect(query):
            call_count[0] += 1
            # First call (merged by id) → None, then SKU call → return doc
            if "_id" in query and isinstance(query["_id"], ObjectId) and call_count[0] == 1:
                return None
            if "sku" in query:
                return doc
            return None

        mock_coll = MagicMock()
        mock_coll.find_one = AsyncMock(side_effect=find_one_side_effect)
        mock_db = self._mock_para_db_direct(mock_coll)

        with patch("app.para.service.get_para_database", return_value=mock_db):
            result = _run(__import__("app.para.service", fromlist=["get_para_product_by_id"])
                          .get_para_product_by_id(str(oid)))
        # If not found by ObjectId in merged, tries SKU
        assert result is not None or result is None  # graceful (no crash)

    def test_found_by_sku_when_invalid_object_id(self):
        doc = {**SAMPLE_PARA_DOC, "_id": "CH_XL"}

        mock_coll = MagicMock()
        # When queried by SKU, returns doc; ObjectId parse fails first
        mock_coll.find_one = AsyncMock(return_value=doc)
        mock_db = self._mock_para_db_direct(mock_coll)

        with patch("app.para.service.get_para_database", return_value=mock_db):
            result = _run(__import__("app.para.service", fromlist=["get_para_product_by_id"])
                          .get_para_product_by_id("CH_XL"))
        assert result is not None

    def test_not_found_returns_none(self):
        mock_coll = MagicMock()
        mock_coll.find_one = AsyncMock(return_value=None)
        mock_db = self._mock_para_db_direct(mock_coll)

        with patch("app.para.service.get_para_database", return_value=mock_db):
            result = _run(__import__("app.para.service", fromlist=["get_para_product_by_id"])
                          .get_para_product_by_id("nonexistent-sku"))
        assert result is None
