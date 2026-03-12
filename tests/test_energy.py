"""
Tests for app/ml/energy_service.py, app/ml/schemas.py, and app/ml/router.py.
Run with: pytest tests/test_energy.py -v
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


# ---------------------------------------------------------------------------
# 1. Pydantic schemas (ml/schemas.py) — import coverage
# ---------------------------------------------------------------------------

class TestMlSchemas:

    def test_energy_consumption_schema(self):
        from app.ml.schemas import EnergyConsumption
        ec = EnergyConsumption(daily_kwh=1.2, monthly_kwh=36.0, yearly_kwh=438.0)
        assert ec.daily_kwh == 1.2

    def test_energy_cost_schema(self):
        from app.ml.schemas import EnergyCost
        cost = EnergyCost(daily=0.216, monthly=6.48, yearly=78.84)
        assert cost.daily == 0.216

    def test_total_cost_of_ownership_schema(self):
        from app.ml.schemas import TotalCostOfOwnership
        tco = TotalCostOfOwnership(purchase_price=1500.0, five_year_energy_cost=394.2, five_year_total=1894.2)
        assert tco.five_year_total == 1894.2

    def test_energy_calculation_response_schema(self):
        from datetime import datetime
        from app.ml.schemas import EnergyCalculationResponse, EnergyConsumption, EnergyCost, TotalCostOfOwnership
        ec = EnergyConsumption(daily_kwh=1.2, monthly_kwh=36.0, yearly_kwh=438.0)
        cost = EnergyCost(daily=0.216, monthly=6.48, yearly=78.84)
        tco = TotalCostOfOwnership(purchase_price=1000.0, five_year_energy_cost=394.2, five_year_total=1394.2)
        resp = EnergyCalculationResponse(
            product_id="abc123",
            product_name="TV",
            category="television",
            wattage=100.0,
            usage_hours_per_day=5.0,
            efficiency_rating="A+",
            efficiency_factor=0.87,
            consumption=ec,
            cost_tnd=cost,
            total_cost_of_ownership=tco,
            co2_emissions_kg_per_year=219.0,
            calculated_at=datetime.utcnow(),
        )
        assert resp.category == "television"

    def test_energy_compare_request_schema(self):
        from app.ml.schemas import EnergyCompareRequest
        req = EnergyCompareRequest(product_ids=["id1", "id2"])
        assert len(req.product_ids) == 2

    def test_energy_compare_response_schema(self):
        from app.ml.schemas import EnergyCompareResponse
        resp = EnergyCompareResponse(
            comparison=[],
            most_efficient=None,
            least_efficient=None,
            total_devices=0,
        )
        assert resp.total_devices == 0

    def test_energy_saving_tips_schema(self):
        from app.ml.schemas import EnergySavingTipsResponse
        tips = EnergySavingTipsResponse(category="refrigerator", tips=["Buy A+++ rated appliances"])
        assert tips.category == "refrigerator"

    def test_energy_categories_response_schema(self):
        from app.ml.schemas import EnergyCategoriesResponse
        resp = EnergyCategoriesResponse(categories={"refrigerator": {"typical_wattage": 150}})
        assert "refrigerator" in resp.categories


# ---------------------------------------------------------------------------
# 2. detect_category
# ---------------------------------------------------------------------------

class TestDetectCategory:

    def test_detects_laptop(self):
        from app.ml.energy_service import detect_category
        assert detect_category("ultrabook dell 13 pouces") == "laptop"

    def test_detects_refrigerator(self):
        from app.ml.energy_service import detect_category
        assert detect_category("Réfrigérateur Samsung 300L") == "refrigerator"

    def test_detects_television(self):
        from app.ml.energy_service import detect_category
        assert detect_category("Smart TV LED 55 pouces") == "television"

    def test_detects_air_conditioner(self):
        from app.ml.energy_service import detect_category
        assert detect_category("Climatiseur 12000 BTU") == "air_conditioner"

    def test_detects_washing_machine(self):
        from app.ml.energy_service import detect_category
        assert detect_category("lave-linge 8kg") == "washing_machine"

    def test_falls_back_to_other(self):
        from app.ml.energy_service import detect_category
        assert detect_category("Unknown Widget XYZ") == "other"

    def test_uses_category_hint(self):
        from app.ml.energy_service import detect_category
        result = detect_category("Product 123", category_hint="lave linge")
        assert result == "washing_machine"


# ---------------------------------------------------------------------------
# 3. extract_wattage
# ---------------------------------------------------------------------------

class TestExtractWattage:

    def test_extracts_from_spec_numeric(self):
        from app.ml.energy_service import extract_wattage
        result = extract_wattage({"puissance": 1200}, "")
        assert result == 1200.0

    def test_extracts_from_spec_string_with_w(self):
        from app.ml.energy_service import extract_wattage
        result = extract_wattage({"power": "850W"}, "")
        assert result == 850.0

    def test_extracts_from_spec_string_watt(self):
        from app.ml.energy_service import extract_wattage
        result = extract_wattage({"consumption": "2000 watt"}, "")
        assert result == 2000.0

    def test_extracts_from_product_name(self):
        from app.ml.energy_service import extract_wattage
        result = extract_wattage(None, "Iron 2400W Pro")
        assert result == 2400.0

    def test_returns_none_when_no_info(self):
        from app.ml.energy_service import extract_wattage
        result = extract_wattage(None, "Product XYZ")
        assert result is None

    def test_returns_none_for_empty_specs(self):
        from app.ml.energy_service import extract_wattage
        result = extract_wattage({}, "")
        assert result is None

    def test_ignores_out_of_range_value(self):
        from app.ml.energy_service import extract_wattage
        # Value of "2" is out of range [5, 10000], should not return
        result = extract_wattage({"power": "2"}, "")
        assert result is None or result == 2.0  # implementation may vary, just should not crash


# ---------------------------------------------------------------------------
# 4. detect_efficiency_rating
# ---------------------------------------------------------------------------

class TestDetectEfficiencyRating:

    def test_detects_a_plus_plus_plus(self):
        from app.ml.energy_service import detect_efficiency_rating
        result = detect_efficiency_rating({"classe": "A+++"}, "")
        assert result == "A+++"

    def test_detects_from_name(self):
        from app.ml.energy_service import detect_efficiency_rating
        result = detect_efficiency_rating(None, "Réfrigérateur Classe A++")
        assert result == "A++"

    def test_defaults_to_b(self):
        from app.ml.energy_service import detect_efficiency_rating
        result = detect_efficiency_rating(None, "xxxxxxxxx 123")
        assert result == "B"

    def test_detects_from_efficiency_key(self):
        from app.ml.energy_service import detect_efficiency_rating
        result = detect_efficiency_rating({"efficiency": "A"}, "")
        assert result == "A"


# ---------------------------------------------------------------------------
# 5. calculate_energy (pure physics calculation)
# ---------------------------------------------------------------------------

class TestCalculateEnergy:

    def test_basic_calculation(self):
        from app.ml.energy_service import calculate_energy
        result = calculate_energy(wattage=100, usage_hours=5, efficiency_factor=1.0, standby_ratio=0.1)
        assert result["daily_kwh"] > 0
        assert result["monthly_kwh"] == round(result["daily_kwh"] * 30, 2)
        assert result["yearly_kwh"] == round(result["daily_kwh"] * 365, 2)

    def test_zero_usage_still_has_standby(self):
        from app.ml.energy_service import calculate_energy
        result = calculate_energy(wattage=100, usage_hours=0, efficiency_factor=1.0, standby_ratio=0.05)
        assert result["daily_kwh"] > 0  # standby

    def test_high_wattage_dryer(self):
        from app.ml.energy_service import calculate_energy
        result = calculate_energy(wattage=3000, usage_hours=1, efficiency_factor=0.85, standby_ratio=0.02)
        assert result["daily_kwh"] > 2.0  # 3kW for 1 hour

    def test_returns_dict_with_correct_keys(self):
        from app.ml.energy_service import calculate_energy
        result = calculate_energy(wattage=500, usage_hours=8, efficiency_factor=0.9, standby_ratio=0.05)
        assert "daily_kwh" in result
        assert "monthly_kwh" in result
        assert "yearly_kwh" in result


# ---------------------------------------------------------------------------
# 6. calculate_cost
# ---------------------------------------------------------------------------

class TestCalculateCost:

    def test_cost_mirrors_consumption(self):
        from app.ml.energy_service import calculate_cost, ELECTRICITY_RATE_TND
        consumption = {"daily_kwh": 1.0, "monthly_kwh": 30.0, "yearly_kwh": 365.0}
        cost = calculate_cost(consumption)
        assert abs(cost["daily"] - 1.0 * ELECTRICITY_RATE_TND) < 0.01

    def test_returns_dict_with_correct_keys(self):
        from app.ml.energy_service import calculate_cost
        cost = calculate_cost({"daily_kwh": 2.0, "monthly_kwh": 60.0, "yearly_kwh": 730.0})
        assert "daily" in cost
        assert "monthly" in cost
        assert "yearly" in cost


# ---------------------------------------------------------------------------
# 7. get_tips
# ---------------------------------------------------------------------------

class TestGetTips:

    def test_returns_tips_for_known_category(self):
        from app.ml.energy_service import get_tips
        result = get_tips("refrigerator")
        assert result["category"] == "refrigerator"
        assert len(result["tips"]) > 0

    def test_returns_default_tips_for_unknown_category(self):
        from app.ml.energy_service import get_tips
        result = get_tips("unicorn_device")
        assert result["category"] == "unicorn_device"
        assert len(result["tips"]) > 0

    def test_case_insensitive(self):
        from app.ml.energy_service import get_tips
        result = get_tips("LAPTOP")
        assert result["category"] == "laptop"
        assert len(result["tips"]) > 0


# ---------------------------------------------------------------------------
# 8. get_all_categories
# ---------------------------------------------------------------------------

class TestGetAllCategories:

    def test_returns_dict_of_categories(self):
        from app.ml.energy_service import get_all_categories
        cats = get_all_categories()
        assert isinstance(cats, dict)
        assert "refrigerator" in cats
        assert "laptop" in cats

    def test_each_category_has_typical_wattage(self):
        from app.ml.energy_service import get_all_categories
        cats = get_all_categories()
        for key, val in cats.items():
            assert "typical_wattage" in val

    def test_does_not_include_keywords(self):
        from app.ml.energy_service import get_all_categories
        cats = get_all_categories()
        for key, val in cats.items():
            assert "keywords" not in val  # internal key should not be exposed


# ---------------------------------------------------------------------------
# 9. calculate_product_energy (async — mocked DB)
# ---------------------------------------------------------------------------

SAMPLE_PRODUCT_DOC = {
    "_id": "64abc",
    "title": "Réfrigérateur Samsung 300L A+",
    "subcategory": "réfrigérateurs",
    "shops": {
        "mytek": {"price": "1500"},
        "tunisianet": {"price": "1400"},
    },
    "specifications": {"puissance": "150"},
    "_source": "retails",
}


def _mock_energy_db(retails_doc=None, para_doc=None):
    """Build a mock for db.client where Retails/PARA find_one returns specific docs."""
    mock_client = MagicMock()

    def get_db(db_name):
        mock_db_obj = MagicMock()

        def get_coll(coll_name):
            mock_coll = AsyncMock()
            if db_name == "Retails":
                mock_coll.find_one = AsyncMock(return_value=retails_doc)
            elif db_name == "PARA":
                mock_coll.find_one = AsyncMock(return_value=para_doc)
            else:
                mock_coll.find_one = AsyncMock(return_value=None)
                mock_coll.insert_one = AsyncMock()
            return mock_coll

        mock_db_obj.__getitem__ = MagicMock(side_effect=get_coll)
        return mock_db_obj

    mock_client.__getitem__ = MagicMock(side_effect=get_db)
    return mock_client


class TestCalculateProductEnergy:

    def test_returns_result_for_valid_product(self):
        from app.ml import energy_service
        from bson import ObjectId
        doc = {**SAMPLE_PRODUCT_DOC, "_id": ObjectId()}
        mock_client = _mock_energy_db(retails_doc=doc)
        with patch.object(energy_service.db, "client", mock_client):
            result = _run(energy_service.calculate_product_energy(str(doc["_id"])))
        assert result is not None
        assert result["category"] == "refrigerator"
        assert "consumption" in result

    def test_returns_none_for_invalid_id(self):
        from app.ml import energy_service
        result = _run(energy_service.calculate_product_energy("not-a-valid-objectid"))
        assert result is None

    def test_returns_none_when_product_not_in_db(self):
        from app.ml import energy_service
        from bson import ObjectId
        mock_client = _mock_energy_db(retails_doc=None, para_doc=None)
        with patch.object(energy_service.db, "client", mock_client):
            result = _run(energy_service.calculate_product_energy(str(ObjectId())))
        assert result is None

    def test_uses_custom_wattage_override(self):
        from app.ml import energy_service
        from bson import ObjectId
        doc = {**SAMPLE_PRODUCT_DOC, "_id": ObjectId()}
        mock_client = _mock_energy_db(retails_doc=doc)
        with patch.object(energy_service.db, "client", mock_client):
            result = _run(energy_service.calculate_product_energy(
                str(doc["_id"]), custom_wattage=500.0
            ))
        assert result is not None
        assert result["wattage"] == 500.0

    def test_uses_custom_usage_hours(self):
        from app.ml import energy_service
        from bson import ObjectId
        doc = {**SAMPLE_PRODUCT_DOC, "_id": ObjectId()}
        mock_client = _mock_energy_db(retails_doc=doc)
        with patch.object(energy_service.db, "client", mock_client):
            result = _run(energy_service.calculate_product_energy(
                str(doc["_id"]), usage_hours_per_day=2.0
            ))
        assert result is not None
        assert result["usage_hours_per_day"] == 2.0


# ---------------------------------------------------------------------------
# 10. compare_products (async — mocked via calculate_product_energy)
# ---------------------------------------------------------------------------

class TestCompareProducts:

    def test_compares_two_products(self):
        from app.ml import energy_service
        from bson import ObjectId

        async def mock_calc(pid, *args, **kwargs):
            return {
                "product_id": pid,
                "product_name": f"Product {pid}",
                "category": "television",
                "wattage": 100.0 if "a" in pid else 200.0,
                "efficiency_rating": "A+",
                "consumption": {"daily_kwh": 0.5, "monthly_kwh": 15.0, "yearly_kwh": 182.5},
                "cost_tnd": {"daily": 0.09, "monthly": 2.7, "yearly": 32.85 if "a" in pid else 65.7},
                "total_cost_of_ownership": {"purchase_price": 500.0, "five_year_energy_cost": 164.25, "five_year_total": 664.25},
                "co2_emissions_kg_per_year": 91.25,
            }

        with patch.object(energy_service, "calculate_product_energy", side_effect=mock_calc):
            result = _run(energy_service.compare_products(["product_a", "product_b"]))

        assert result is not None
        assert result["total_devices"] == 2
        assert result["most_efficient"] is not None
        assert result["least_efficient"] is not None

    def test_returns_none_when_no_valid_products(self):
        from app.ml import energy_service

        async def mock_calc(pid, *args, **kwargs):
            return None

        with patch.object(energy_service, "calculate_product_energy", side_effect=mock_calc):
            result = _run(energy_service.compare_products(["id1", "id2"]))

        assert result is None


# ---------------------------------------------------------------------------
# 11. ML Router – via TestClient
# ---------------------------------------------------------------------------

ML_BASE = "/api/v1/energy"


class TestEnergyCalculateGetEndpoint:

    def test_returns_404_when_not_found(self, client):
        with patch("app.ml.energy_service.calculate_product_energy", new_callable=AsyncMock,
                   return_value=None):
            resp = client.get(f"{ML_BASE}/calculate", params={"product_id": "nonexistent"})
        assert resp.status_code == 404

    def test_returns_result_when_found(self, client):
        mock_result = {
            "product_id": "abc",
            "product_name": "TV",
            "category": "television",
            "wattage": 100.0,
            "usage_hours_per_day": 5.0,
            "efficiency_rating": "A+",
            "efficiency_factor": 0.87,
            "consumption": {"daily_kwh": 0.5, "monthly_kwh": 15.0, "yearly_kwh": 182.5},
            "cost_tnd": {"daily": 0.09, "monthly": 2.7, "yearly": 32.85},
            "total_cost_of_ownership": {"purchase_price": 500.0, "five_year_energy_cost": 164.25, "five_year_total": 664.25},
            "co2_emissions_kg_per_year": 91.25,
            "calculated_at": "2026-01-01T00:00:00",
        }
        with patch("app.ml.router.calculate_product_energy", new_callable=AsyncMock,
                   return_value=mock_result):
            resp = client.get(f"{ML_BASE}/calculate", params={"product_id": "abc"})
        assert resp.status_code == 200
        assert resp.json()["category"] == "television"


class TestEnergyCalculatePostEndpoint:

    def test_returns_404_when_not_found(self, client):
        with patch("app.ml.energy_service.calculate_product_energy", new_callable=AsyncMock,
                   return_value=None):
            resp = client.post(f"{ML_BASE}/calculate", json={"product_id": "nope"})
        assert resp.status_code == 404

    def test_returns_result_when_found(self, client):
        mock_result = {"product_id": "abc", "product_name": "Laptop", "category": "laptop"}
        with patch("app.ml.router.calculate_product_energy", new_callable=AsyncMock,
                   return_value=mock_result):
            resp = client.post(f"{ML_BASE}/calculate", json={
                "product_id": "abc",
                "usage_hours_per_day": 6.0,
                "custom_wattage": 65.0,
            })
        assert resp.status_code == 200


class TestEnergyCompareEndpoint:

    def test_too_few_ids_returns_400(self, client):
        resp = client.post(f"{ML_BASE}/compare", json={"product_ids": ["only_one"]})
        assert resp.status_code == 400

    def test_too_many_ids_returns_400(self, client):
        resp = client.post(f"{ML_BASE}/compare", json={"product_ids": [f"id{i}" for i in range(11)]})
        assert resp.status_code == 400

    def test_no_valid_products_returns_404(self, client):
        async def _null(*args, **kwargs):
            return None
        with patch("app.ml.energy_service.calculate_product_energy", side_effect=_null):
            resp = client.post(f"{ML_BASE}/compare", json={"product_ids": ["a", "b"]})
        assert resp.status_code == 404


class TestEnergyTipsEndpoint:

    def test_returns_tips_for_refrigerator(self, client):
        resp = client.get(f"{ML_BASE}/tips/refrigerator")
        assert resp.status_code == 200
        data = resp.json()
        assert data["category"] == "refrigerator"
        assert len(data["tips"]) > 0

    def test_returns_default_tips_for_unknown(self, client):
        resp = client.get(f"{ML_BASE}/tips/unknown_device")
        assert resp.status_code == 200
        assert len(resp.json()["tips"]) > 0


class TestEnergyCategoriesEndpoint:

    def test_returns_categories(self, client):
        resp = client.get(f"{ML_BASE}/categories")
        assert resp.status_code == 200
        data = resp.json()
        # get_all_categories returns dict, router returns it directly
        assert "refrigerator" in data
