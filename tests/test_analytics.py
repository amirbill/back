"""
Tests for app/analytics/service.py and app/analytics/router.py.
Run with: pytest tests/test_analytics.py -v
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


def _mock_db_for_analytics(retails_doc, para_doc=None):
    """Build a mock db whose specific collection.find_one returns the right doc."""
    mock_db = MagicMock()
    mock_client = MagicMock()
    mock_db.client = mock_client

    def side_effect_db(db_name):
        mock_collection_holder = MagicMock()

        def side_effect_coll(coll_name):
            mock_coll = AsyncMock()
            if db_name == "Retails":
                mock_coll.find_one = AsyncMock(return_value=retails_doc)
            elif db_name == "PARA":
                mock_coll.find_one = AsyncMock(return_value=para_doc)
            else:
                mock_coll.find_one = AsyncMock(return_value=None)
            mock_coll.distinct = AsyncMock(return_value=[])
            return mock_coll

        mock_collection_holder.__getitem__ = MagicMock(side_effect=side_effect_coll)
        return mock_collection_holder

    mock_client.__getitem__ = MagicMock(side_effect=side_effect_db)
    return mock_db


# ---------------------------------------------------------------------------
# Sample documents
# ---------------------------------------------------------------------------

RETAILS_ANALYTICS_DOC = {
    "analytics": {
        "shops": {
            "mytek": {
                "average_price": 1500.0,
                "product_count": 200,
                "available_count": 180,
                "total_price": 300000.0,
                "cheapest_product_count": 50,
                "discount_count": 30,
                "total_discount_value": 4500.0,
                "average_discount_percent": 15.0,
            },
            "oxtek": {  # should be normalised to 'technopro'
                "average_price": 1600.0,
                "product_count": 100,
                "available_count": 90,
                "total_price": 160000.0,
                "cheapest_product_count": 20,
                "discount_count": 10,
                "total_discount_value": 2000.0,
                "average_discount_percent": 12.5,
            },
        }
    },
    "merge_stats": {
        "mytek_total": 500,
        "tunisianet_total": 400,
        "common_products": 150,
    },
}

PARA_ANALYTICS_DOC = {
    "analytics": {
        "shops": [
            {"shop_name": "parashop", "average_price": 25.0},
            {"name": "pharma-shop", "average_price": 28.5},
        ]
    },
    "merge_stats": {
        "parashop_total": 300,
        "paramedical_total": 200,
        "common_products": 80,
    },
}


# ---------------------------------------------------------------------------
# 1. normalize_shop_name
# ---------------------------------------------------------------------------

class TestNormalizeShopName:

    def test_oxtek_maps_to_technopro(self):
        from app.analytics.service import normalize_shop_name
        assert normalize_shop_name("oxtek") == "technopro"

    def test_unknown_name_returned_unchanged(self):
        from app.analytics.service import normalize_shop_name
        assert normalize_shop_name("mytek") == "mytek"

    def test_case_insensitive(self):
        from app.analytics.service import normalize_shop_name
        assert normalize_shop_name("OXTEK") == "technopro"


# ---------------------------------------------------------------------------
# 2. get_shop_prices
# ---------------------------------------------------------------------------

class TestGetShopPrices:

    def test_retails_dict_format(self):
        from app.analytics import service
        mock_db = _mock_db_for_analytics(RETAILS_ANALYTICS_DOC, None)
        with patch.object(service, "get_database", return_value=mock_db):
            result = _run(service.get_shop_prices())
        names = [s.name for s in result]
        assert "mytek" in names
        # oxtek should be normalised
        assert "technopro" in names
        assert "oxtek" not in names

    def test_para_list_format(self):
        from app.analytics import service
        mock_db = _mock_db_for_analytics(None, PARA_ANALYTICS_DOC)
        with patch.object(service, "get_database", return_value=mock_db):
            result = _run(service.get_shop_prices())
        names = [s.name for s in result]
        assert "parashop" in names
        assert "pharma-shop" in names

    def test_returns_empty_on_error(self):
        from app.analytics import service
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_db.client = mock_client
        mock_client.__getitem__.return_value.__getitem__.return_value.find_one = AsyncMock(
            side_effect=Exception("DB error")
        )
        with patch.object(service, "get_database", return_value=mock_db):
            result = _run(service.get_shop_prices())
        assert isinstance(result, list)

    def test_no_client_returns_empty(self):
        from app.analytics import service
        mock_db = MagicMock()
        mock_db.client = None
        with patch.object(service, "get_database", return_value=mock_db):
            result = _run(service.get_shop_prices())
        assert result == []


# ---------------------------------------------------------------------------
# 3. get_merge_stats
# ---------------------------------------------------------------------------

class TestGetMergeStats:

    def test_both_databases_populated(self):
        from app.analytics import service
        mock_db = _mock_db_for_analytics(RETAILS_ANALYTICS_DOC, PARA_ANALYTICS_DOC)
        with patch.object(service, "get_database", return_value=mock_db):
            result = _run(service.get_merge_stats())

        assert result.retails is not None
        assert result.para is not None
        assert result.retails.common_products == 150
        assert result.para.common_products == 80

    def test_shop_totals_extracted(self):
        from app.analytics import service
        mock_db = _mock_db_for_analytics(RETAILS_ANALYTICS_DOC, None)
        with patch.object(service, "get_database", return_value=mock_db):
            result = _run(service.get_merge_stats())

        assert "mytek_total" in result.retails.shop_totals
        assert result.retails.shop_totals["mytek_total"] == 500

    def test_missing_merge_stats_key(self):
        from app.analytics import service
        doc_no_stats = {"analytics": {}}
        mock_db = _mock_db_for_analytics(doc_no_stats, None)
        with patch.object(service, "get_database", return_value=mock_db):
            result = _run(service.get_merge_stats())

        # retails should be None since doc has no merge_stats
        assert result.retails is None

    def test_returns_empty_on_db_error(self):
        from app.analytics import service
        mock_db = MagicMock()
        mock_db.client = MagicMock()
        mock_db.client.__getitem__.return_value.__getitem__.return_value.find_one = AsyncMock(
            side_effect=Exception("timeout")
        )
        with patch.object(service, "get_database", return_value=mock_db):
            result = _run(service.get_merge_stats())

        assert result.para is None
        assert result.retails is None

    def test_oxtek_normalised_in_shop_totals(self):
        from app.analytics import service
        doc = {
            "merge_stats": {
                "oxtek_total": 99,
                "common_products": 0,
            }
        }
        mock_db = _mock_db_for_analytics(doc, None)
        with patch.object(service, "get_database", return_value=mock_db):
            result = _run(service.get_merge_stats())

        assert "technopro_total" in result.retails.shop_totals


# ---------------------------------------------------------------------------
# 4. get_detailed_shop_analytics
# ---------------------------------------------------------------------------

class TestGetDetailedShopAnalytics:

    def test_retails_shops_parsed(self):
        from app.analytics import service
        mock_db = _mock_db_for_analytics(RETAILS_ANALYTICS_DOC, None)
        with patch.object(service, "get_database", return_value=mock_db):
            result = _run(service.get_detailed_shop_analytics())

        assert len(result.retails_shops) == 2
        names = [s.name for s in result.retails_shops]
        assert "mytek" in names
        assert "technopro" in names   # oxtek normalised

    def test_para_shops_parsed(self):
        from app.analytics import service
        # Para doc needs dict format for shops
        para_doc_dict = {
            "analytics": {
                "shops": {
                    "parashop": {
                        "product_count": 300,
                        "available_count": 280,
                        "total_price": 8400.0,
                        "average_price": 28.0,
                        "cheapest_product_count": 120,
                        "discount_count": 45,
                        "total_discount_value": 900.0,
                        "average_discount_percent": 8.5,
                    }
                }
            }
        }
        mock_db = _mock_db_for_analytics(None, para_doc_dict)
        with patch.object(service, "get_database", return_value=mock_db):
            result = _run(service.get_detailed_shop_analytics())

        assert len(result.para_shops) == 1
        assert result.para_shops[0].name == "parashop"
        assert result.para_shops[0].product_count == 300

    def test_empty_on_error(self):
        from app.analytics import service
        mock_db = MagicMock()
        mock_db.client = MagicMock()
        mock_db.client.__getitem__.return_value.__getitem__.return_value.find_one = AsyncMock(
            side_effect=Exception("err")
        )
        with patch.object(service, "get_database", return_value=mock_db):
            result = _run(service.get_detailed_shop_analytics())

        assert result.para_shops == []
        assert result.retails_shops == []


# ---------------------------------------------------------------------------
# 5. Router tests (via TestClient from conftest)
# ---------------------------------------------------------------------------

BASE = "/api/v1/analytics"


class TestAnalyticsPricesEndpoint:

    def test_returns_shop_list(self, client):
        from app.analytics.schemas import ShopAnalytics
        shops = [ShopAnalytics(name="mytek", average_price=1500.0)]
        with patch("app.analytics.service.get_shop_prices", new_callable=AsyncMock, return_value=shops):
            resp = client.get(f"{BASE}/prices")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["name"] == "mytek"

    def test_returns_500_on_error(self, client):
        with patch("app.analytics.service.get_shop_prices", new_callable=AsyncMock,
                   side_effect=Exception("db down")):
            resp = client.get(f"{BASE}/prices")
        assert resp.status_code == 500


class TestAnalyticsMergeStatsEndpoint:

    def test_returns_merge_stats(self, client):
        from app.analytics.schemas import MergeStatsResponse, MergeStats
        stats = MergeStatsResponse(
            para=MergeStats(shop_totals={"parashop_total": 300}, common_products=80),
            retails=None,
        )
        with patch("app.analytics.service.get_merge_stats", new_callable=AsyncMock, return_value=stats):
            resp = client.get(f"{BASE}/merge-stats")
        assert resp.status_code == 200
        assert resp.json()["para"]["common_products"] == 80

    def test_returns_500_on_error(self, client):
        with patch("app.analytics.service.get_merge_stats", new_callable=AsyncMock,
                   side_effect=Exception("fail")):
            resp = client.get(f"{BASE}/merge-stats")
        assert resp.status_code == 500


class TestAnalyticsShopDetailsEndpoint:

    def test_returns_detailed_analytics(self, client):
        from app.analytics.schemas import DetailedAnalyticsResponse, ShopDetailedAnalytics
        s = ShopDetailedAnalytics(
            name="mytek",
            product_count=200,
            available_count=180,
            total_price=300000.0,
            average_price=1500.0,
            cheapest_product_count=50,
            discount_count=30,
            total_discount_value=4500.0,
            average_discount_percent=15.0,
        )
        analytics = DetailedAnalyticsResponse(para_shops=[], retails_shops=[s])
        with patch("app.analytics.service.get_detailed_shop_analytics",
                   new_callable=AsyncMock, return_value=analytics):
            resp = client.get(f"{BASE}/shop-details")
        assert resp.status_code == 200
        assert resp.json()["retails_shops"][0]["name"] == "mytek"

    def test_returns_500_on_error(self, client):
        with patch("app.analytics.service.get_detailed_shop_analytics",
                   new_callable=AsyncMock, side_effect=Exception("fail")):
            resp = client.get(f"{BASE}/shop-details")
        assert resp.status_code == 500


class TestStoreProductsAdded:

    def test_service_returns_products_added_rows(self):
        from app.analytics import service

        doc = {
            "_id": "abc123",
            "shop": "mytek",
            "title": "Ecran HP",
            "price": 569,
            "sku": "94C19AS",
            "available": True,
            "images": ["https://img.example/test.jpg"],
            "specifications": {"Marque": "HP"},
            "store_availability": [{"store": "Tunis", "status": "En stock", "available": True}],
        }

        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_db.client = mock_client
        collection = MagicMock()
        cursor = MagicMock()
        cursor.sort.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.to_list = AsyncMock(return_value=[doc])
        collection.find.return_value = cursor
        mock_client.__getitem__.return_value.__getitem__.return_value = collection

        with patch.object(service, "get_database", return_value=mock_db):
            result = _run(service.get_store_products_added("mytek"))

        assert result.shop == "mytek"
        assert result.total == 1
        assert result.products_added[0].title == "Ecran HP"
        assert result.products_added[0].store_availability[0].store == "Tunis"

    def test_endpoint_returns_products_added(self, client):
        from app.analytics.schemas import StoreProductsAddedResponse, StoreProductAdded

        payload = StoreProductsAddedResponse(
            shop="mytek",
            source="retails",
            total=1,
            products_added=[
                StoreProductAdded(
                    id="abc123",
                    shop="mytek",
                    title="Ecran HP",
                    price=569.0,
                    available=True,
                )
            ],
        )

        with patch("app.analytics.service.get_store_products_added", new_callable=AsyncMock, return_value=payload):
            resp = client.get(f"{BASE}/store-products-added/mytek")

        assert resp.status_code == 200
        assert resp.json()["products_added"][0]["title"] == "Ecran HP"
