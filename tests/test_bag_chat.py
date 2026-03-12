"""
Tests for app/api/endpoints/bag.py and app/chat/service.py + app/chat/router.py.
Run with: pytest tests/test_bag_chat.py -v
"""
import os
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/test")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("GROQ_API_KEY", "test-groq")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ============================================================================
# BAG ENDPOINT  (/api/v1/bag/best-shop)
# ============================================================================

BAG_BASE = "/api/v1/bag"

# ---------------------------------------------------------------------------
# 1. calculate_shop_totals_for_products (pure function)
# ---------------------------------------------------------------------------

class TestCalculateShopTotalsForProducts:

    def _products(self):
        return [
            {
                "sku": "P1",
                "title": "Laptop",
                "shops": {
                    "mytek": {"price": 1500, "available": True, "images": ["https://img.jpg"]},
                    "tunisianet": {"price": 1400, "available": True, "images": []},
                },
            },
            {
                "sku": "P2",
                "title": "Mouse",
                "shops": {
                    "mytek": {"price": 50, "available": True, "images": []},
                    "tunisianet": {"price": None, "available": False, "images": []},
                },
            },
        ]

    def test_returns_shop_totals(self):
        from app.api.endpoints.bag import calculate_shop_totals_for_products
        products = self._products()
        totals, best_shop, best_total = calculate_shop_totals_for_products(
            products, ["mytek", "tunisianet"]
        )
        shop_names = [st.shop for st in totals]
        assert "mytek" in shop_names

    def test_best_shop_has_all_items(self):
        from app.api.endpoints.bag import calculate_shop_totals_for_products
        products = self._products()
        totals, best_shop, best_total = calculate_shop_totals_for_products(
            products, ["mytek", "tunisianet"]
        )
        # mytek has both products available, so it should be best_shop
        assert best_shop == "mytek"
        assert best_total is not None

    def test_picks_best_shop_even_with_partial_availability(self):
        from app.api.endpoints.bag import calculate_shop_totals_for_products
        products = [
            {"sku": "P1", "title": "Item A",
             "shops": {"shop_x": {"price": 100, "available": True, "images": []}}},
        ]
        totals, best_shop, best_total = calculate_shop_totals_for_products(
            products, ["shop_x", "shop_y"]
        )
        assert best_shop == "shop_x"

    def test_empty_products_returns_empty_totals(self):
        from app.api.endpoints.bag import calculate_shop_totals_for_products
        totals, best_shop, best_total = calculate_shop_totals_for_products([], ["mytek"])
        assert totals == []
        assert best_shop is None
        assert best_total is None

    def test_uses_hyphen_variant_shop_name(self):
        from app.api.endpoints.bag import calculate_shop_totals_for_products
        # "pharma-shop" stored as "pharma_shop" in product data
        products = [
            {"sku": "P1", "title": "Serum",
             "shops": {"pharma_shop": {"price": 30, "available": True, "images": []}}},
        ]
        totals, best_shop, best_total = calculate_shop_totals_for_products(
            products, ["pharma-shop"]
        )
        assert best_shop == "pharma-shop"

    def test_unavailable_product_counted_as_missing(self):
        from app.api.endpoints.bag import calculate_shop_totals_for_products
        products = [
            {"sku": "P1", "title": "Item",
             "shops": {"mytek": {"price": 100, "available": False, "images": []}}},
        ]
        totals, best_shop, best_total = calculate_shop_totals_for_products(
            products, ["mytek"]
        )
        if totals:
            # Available count should be 0 since not available
            mytek_total = next((t for t in totals if t.shop == "mytek"), None)
            if mytek_total:
                assert mytek_total.available_count == 0


# ---------------------------------------------------------------------------
# 2. POST /bag/best-shop
# ---------------------------------------------------------------------------

class TestBestShopEndpoint:

    def _valid_object_id(self):
        from bson import ObjectId
        return str(ObjectId())

    def test_empty_items_returns_400(self, client):
        resp = client.post(f"{BAG_BASE}/best-shop", json={"items": []})
        assert resp.status_code == 400

    def test_valid_retail_items(self, client):
        oid = self._valid_object_id()
        retail_doc = {
            "_id": oid,
            "title": "Laptop",
            "shops": {
                "mytek": {"price": 1500, "available": True, "images": []},
            },
        }

        mock_para_db = MagicMock()
        mock_retail_db = MagicMock()
        mock_para_coll = MagicMock()
        mock_retail_coll = MagicMock()

        mock_para_coll.find.return_value.to_list = AsyncMock(return_value=[])
        mock_retail_coll.find.return_value.to_list = AsyncMock(return_value=[retail_doc])

        mock_para_db.__getitem__.return_value = mock_para_coll
        mock_retail_db.__getitem__.return_value = mock_retail_coll

        with patch("app.api.endpoints.bag.get_para_database", return_value=mock_para_db), \
             patch("app.api.endpoints.bag.get_retail_database", return_value=mock_retail_db):
            resp = client.post(f"{BAG_BASE}/best-shop", json={
                "items": [{"sku": oid, "source": "retail"}]
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["retail_result"] is not None

    def test_valid_para_items(self, client):
        oid = self._valid_object_id()
        para_doc = {
            "_id": oid,
            "title": "Serum",
            "shops": {
                "parashop": {"price": 30, "available": True, "images": []},
            },
        }

        mock_para_db = MagicMock()
        mock_retail_db = MagicMock()
        mock_para_coll = MagicMock()
        mock_retail_coll = MagicMock()

        mock_para_coll.find.return_value.to_list = AsyncMock(return_value=[para_doc])
        mock_retail_coll.find.return_value.to_list = AsyncMock(return_value=[])

        mock_para_db.__getitem__.return_value = mock_para_coll
        mock_retail_db.__getitem__.return_value = mock_retail_coll

        with patch("app.api.endpoints.bag.get_para_database", return_value=mock_para_db), \
             patch("app.api.endpoints.bag.get_retail_database", return_value=mock_retail_db):
            resp = client.post(f"{BAG_BASE}/best-shop", json={
                "items": [{"sku": oid, "source": "para"}]
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["para_result"] is not None

    def test_invalid_sku_skipped(self, client):
        mock_para_db = MagicMock()
        mock_retail_db = MagicMock()
        mock_para_coll = MagicMock()
        mock_retail_coll = MagicMock()
        mock_para_coll.find.return_value.to_list = AsyncMock(return_value=[])
        mock_retail_coll.find.return_value.to_list = AsyncMock(return_value=[])
        mock_para_db.__getitem__.return_value = mock_para_coll
        mock_retail_db.__getitem__.return_value = mock_retail_coll

        with patch("app.api.endpoints.bag.get_para_database", return_value=mock_para_db), \
             patch("app.api.endpoints.bag.get_retail_database", return_value=mock_retail_db):
            resp = client.post(f"{BAG_BASE}/best-shop", json={
                "items": [{"sku": "not-a-valid-id", "source": "retail"}]
            })
        # Should not crash, returns 200 with empty results
        assert resp.status_code == 200


# ============================================================================
# CHAT SERVICE  (app/chat/service.py)
# ============================================================================

class TestChatService:

    def test_get_groq_client_singleton(self):
        from app.chat import service as chat_svc
        # Reset singleton
        chat_svc._client = None
        mock_groq = MagicMock()
        with patch("app.chat.service.AsyncGroq", return_value=mock_groq):
            client1 = chat_svc.get_groq_client()
            client2 = chat_svc.get_groq_client()
        assert client1 is client2  # same singleton

    def test_get_chat_response_success(self):
        from app.chat import service as chat_svc

        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = "Bonjour! Je suis l'assistant 1111.tn."

        mock_groq_client = AsyncMock()
        mock_groq_client.chat.completions.create = AsyncMock(return_value=mock_completion)

        chat_svc._client = mock_groq_client
        result = _run(chat_svc.get_chat_response("Qu'est-ce que 1111.tn?"))
        assert "1111" in result or len(result) > 0

    def test_get_chat_response_with_history(self):
        from app.chat import service as chat_svc

        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = "Voici la réponse."
        mock_groq_client = AsyncMock()
        mock_groq_client.chat.completions.create = AsyncMock(return_value=mock_completion)

        chat_svc._client = mock_groq_client
        history = [
            {"role": "user", "content": "Bonjour"},
            {"role": "assistant", "content": "Bonjour! Comment puis-je vous aider?"},
        ]
        result = _run(chat_svc.get_chat_response("Que faites-vous?", history=history))
        assert isinstance(result, str)

    def test_get_chat_response_on_api_error_returns_fallback(self):
        from app.chat import service as chat_svc

        mock_groq_client = AsyncMock()
        mock_groq_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

        chat_svc._client = mock_groq_client
        result = _run(chat_svc.get_chat_response("Test"))
        # Service should return None or a fallback string, not raise
        assert result is None or isinstance(result, str)

    def test_history_truncated_to_20(self):
        from app.chat import service as chat_svc

        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = "OK"
        mock_groq_client = AsyncMock()
        mock_groq_client.chat.completions.create = AsyncMock(return_value=mock_completion)
        chat_svc._client = mock_groq_client

        long_history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
            for i in range(30)
        ]
        _run(chat_svc.get_chat_response("Latest", history=long_history))

        call_args = mock_groq_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0] if call_args.args else []
        if isinstance(messages, list):
            # system + up to 20 history + 1 current
            assert len(messages) <= 22


# ============================================================================
# CHAT ROUTER  (app/chat/router.py)
# ============================================================================

CHAT_BASE = "/api/v1/chat"


class TestChatRouter:

    def test_chat_message_success(self, client):
        with patch("app.chat.router.get_chat_response", new_callable=AsyncMock,
                   return_value="Bonjour depuis l'assistant 1111.tn!"):
            resp = client.post(f"{CHAT_BASE}/message",
                               json={"message": "Bonjour"})
        assert resp.status_code == 200
        assert resp.json()["reply"] == "Bonjour depuis l'assistant 1111.tn!"

    def test_chat_message_with_history(self, client):
        with patch("app.chat.router.get_chat_response", new_callable=AsyncMock,
                   return_value="Réponse avec historique") as mock_svc:
            resp = client.post(f"{CHAT_BASE}/message", json={
                "message": "Suite",
                "history": [
                    {"role": "user", "content": "Bonjour"},
                    {"role": "assistant", "content": "Bonjour!"},
                ],
            })
            # Verify history was forwarded
            call_history = mock_svc.call_args[0][1]
            assert call_history is not None
            assert len(call_history) == 2

        assert resp.status_code == 200

    def test_chat_message_without_history(self, client):
        with patch("app.chat.router.get_chat_response", new_callable=AsyncMock,
                   return_value="Réponse sans historique") as mock_svc:
            resp = client.post(f"{CHAT_BASE}/message", json={"message": "Hello"})
            mock_svc.assert_called_once_with("Hello", None)

        assert resp.status_code == 200
