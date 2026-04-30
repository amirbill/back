from pydantic import BaseModel
from typing import List, Optional, Dict

class ShopAnalytics(BaseModel):
    name: str
    average_price: float
    logo_url: Optional[str] = None # Helper for frontend, though we map locally too

class AnalyticsResponse(BaseModel):
    shops: List[ShopAnalytics]

# New schemas for merge stats
class MergeStats(BaseModel):
    shop_totals: Dict[str, int]  # e.g., {"parashop_total": 4571, "pharma_shop_total": 2995, ...}
    common_products: int

class MergeStatsResponse(BaseModel):
    para: Optional[MergeStats] = None
    retails: Optional[MergeStats] = None

# Detailed shop analytics
class ShopDetailedAnalytics(BaseModel):
    name: str
    product_count: int
    available_count: int
    total_price: float
    average_price: float
    cheapest_product_count: int
    discount_count: int
    total_discount_value: float
    average_discount_percent: float

class DetailedAnalyticsResponse(BaseModel):
    para_shops: List[ShopDetailedAnalytics]
    retails_shops: List[ShopDetailedAnalytics]


class StoreAvailabilityEntry(BaseModel):
    store: str
    status: Optional[str] = None
    available: bool = False


class StoreProductAdded(BaseModel):
    id: str
    url: Optional[str] = None
    shop: str
    scraped_at: Optional[str] = None
    updated_at: Optional[str] = None
    top_category: Optional[str] = None
    low_category: Optional[str] = None
    subcategory: Optional[str] = None
    title: str
    product_id: Optional[str] = None
    sku: Optional[str] = None
    overview: Optional[str] = None
    brand_logo: Optional[str] = None
    brand: Optional[str] = None
    price: Optional[float] = None
    specifications: Dict[str, str] = {}
    images: List[str] = []
    availability: Optional[str] = None
    available: bool = False
    store_availability: List[StoreAvailabilityEntry] = []


class StoreProductsAddedResponse(BaseModel):
    shop: str
    source: str
    total: int
    products_added: List[StoreProductAdded]


class StoreProductsRemovedResponse(BaseModel):
    shop: str
    source: str
    total: int
    products_removed: List[StoreProductAdded]
