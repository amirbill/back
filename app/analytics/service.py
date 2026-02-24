from app.db.mongodb import get_database
from typing import List, Dict, Optional
from app.analytics.schemas import (
    ShopAnalytics, 
    MergeStats, 
    MergeStatsResponse,
    ShopDetailedAnalytics,
    DetailedAnalyticsResponse
)

# Mapping for shop name normalization (DB name → canonical name)
SHOP_NAME_MAP = {
    "oxtek": "technopro",
}

def normalize_shop_name(name: str) -> str:
    """Normalize shop names to handle renames (e.g., oxtek → technopro)"""
    return SHOP_NAME_MAP.get(name.lower(), name)

async def get_shop_prices() -> List[ShopAnalytics]:
    db = get_database()
    client = db.client
    shops_data = []

    # Helper function to parse shops from a doc
    def parse_shops(doc):
        extracted = []
        if doc and "analytics" in doc and "shops" in doc["analytics"]:
            raw_shops = doc["analytics"]["shops"]
            if isinstance(raw_shops, list):
                for shop in raw_shops:
                    name = shop.get("shop_name") or shop.get("name") or "Unknown"
                    name = normalize_shop_name(name)
                    avg_price = shop.get("average_price", 0.0)
                    extracted.append(ShopAnalytics(name=name, average_price=avg_price))
            elif isinstance(raw_shops, dict):
                for name, data in raw_shops.items():
                    if isinstance(data, dict):
                        normalized_name = normalize_shop_name(name)
                        avg_price = data.get("average_price", 0.0)
                        extracted.append(ShopAnalytics(name=normalized_name, average_price=avg_price))
        return extracted

    # Fetch from Retails (E-commerce)
    try:
        if client:
            doc_retails = await client["Retails"]["merged_analytics"].find_one()
            shops_data.extend(parse_shops(doc_retails))
    except Exception as e:
        print(f"Error fetching from Retails: {e}")

    # Fetch from PARA (Parapharmacie)
    try:
        if client:
            doc_para = await client["PARA"]["merged_analytics"].find_one()
            shops_data.extend(parse_shops(doc_para))
    except Exception as e:
        print(f"Error fetching from PARA: {e}")

    return shops_data


async def get_merge_stats() -> MergeStatsResponse:
    """Fetch merge statistics from both PARA and Retails databases"""
    db = get_database()
    client = db.client
    
    para_stats = None
    retails_stats = None
    
    # Fetch from PARA
    try:
        if client:
            doc_para = await client["PARA"]["merged_analytics"].find_one()
            if doc_para and "merge_stats" in doc_para:
                merge_stats = doc_para["merge_stats"]
                # Extract shop totals dynamically, normalizing shop names
                shop_totals = {}
                for k, v in merge_stats.items():
                    if k.endswith("_total"):
                        prefix = k.rsplit("_total", 1)[0]
                        normalized = normalize_shop_name(prefix)
                        shop_totals[f"{normalized}_total"] = v
                common_products = merge_stats.get("common_products", 0)
                para_stats = MergeStats(shop_totals=shop_totals, common_products=common_products)
    except Exception as e:
        print(f"Error fetching PARA merge stats: {e}")
    
    # Fetch from Retails
    try:
        if client:
            doc_retails = await client["Retails"]["merged_analytics"].find_one()
            if doc_retails and "merge_stats" in doc_retails:
                merge_stats = doc_retails["merge_stats"]
                # Extract shop totals dynamically, normalizing shop names
                shop_totals = {}
                for k, v in merge_stats.items():
                    if k.endswith("_total"):
                        prefix = k.rsplit("_total", 1)[0]
                        normalized = normalize_shop_name(prefix)
                        shop_totals[f"{normalized}_total"] = v
                common_products = merge_stats.get("common_products", 0)
                retails_stats = MergeStats(shop_totals=shop_totals, common_products=common_products)
    except Exception as e:
        print(f"Error fetching Retails merge stats: {e}")
    
    return MergeStatsResponse(para=para_stats, retails=retails_stats)


async def get_detailed_shop_analytics() -> DetailedAnalyticsResponse:
    """Fetch detailed shop analytics from both PARA and Retails databases"""
    db = get_database()
    client = db.client
    
    para_shops = []
    retails_shops = []
    
    # Fetch from PARA
    try:
        if client:
            doc_para = await client["PARA"]["merged_analytics"].find_one()
            if doc_para and "analytics" in doc_para and "shops" in doc_para["analytics"]:
                shops = doc_para["analytics"]["shops"]
                if isinstance(shops, dict):
                    for shop_name, shop_data in shops.items():
                        if isinstance(shop_data, dict):
                            para_shops.append(ShopDetailedAnalytics(
                                name=normalize_shop_name(shop_name),
                                product_count=shop_data.get("product_count", 0),
                                available_count=shop_data.get("available_count", 0),
                                total_price=shop_data.get("total_price", 0.0),
                                average_price=shop_data.get("average_price", 0.0),
                                cheapest_product_count=shop_data.get("cheapest_product_count", 0),
                                discount_count=shop_data.get("discount_count", 0),
                                total_discount_value=shop_data.get("total_discount_value", 0.0),
                                average_discount_percent=shop_data.get("average_discount_percent", 0.0)
                            ))
    except Exception as e:
        print(f"Error fetching PARA shop analytics: {e}")
    
    # Fetch from Retails
    try:
        if client:
            doc_retails = await client["Retails"]["merged_analytics"].find_one()
            if doc_retails and "analytics" in doc_retails and "shops" in doc_retails["analytics"]:
                shops = doc_retails["analytics"]["shops"]
                if isinstance(shops, dict):
                    for shop_name, shop_data in shops.items():
                        if isinstance(shop_data, dict):
                            retails_shops.append(ShopDetailedAnalytics(
                                name=normalize_shop_name(shop_name),
                                product_count=shop_data.get("product_count", 0),
                                available_count=shop_data.get("available_count", 0),
                                total_price=shop_data.get("total_price", 0.0),
                                average_price=shop_data.get("average_price", 0.0),
                                cheapest_product_count=shop_data.get("cheapest_product_count", 0),
                                discount_count=shop_data.get("discount_count", 0),
                                total_discount_value=shop_data.get("total_discount_value", 0.0),
                                average_discount_percent=shop_data.get("average_discount_percent", 0.0)
                            ))
    except Exception as e:
        print(f"Error fetching Retails shop analytics: {e}")
    
    return DetailedAnalyticsResponse(para_shops=para_shops, retails_shops=retails_shops)
