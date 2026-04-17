from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class ShopPrice(BaseModel):
    shop: str
    price: float
    oldPrice: Optional[float] = None
    available: bool = False
    url: Optional[str] = None

class ProductBase(BaseModel):
    id: str
    name: str
    brand: str
    bestPrice: float
    originalPrice: Optional[float] = None
    image: str
    description: str
    inStock: bool
    category: Optional[str] = None
    shopPrices: List[ShopPrice] = []
    specifications: Optional[Dict[str, Any]] = None

class Product(ProductBase):
    pass

class ProductList(BaseModel):
    products: List[Product]

class ProductListResponse(BaseModel):
    products: List[Product]
    total: int
    page: int
    limit: int
    totalPages: int

class SearchResult(BaseModel):
    id: str
    name: str
    brand: str
    bestPrice: float
    image: str
    inStock: bool
    relevance: Optional[float] = None

# Analytics schemas for category price comparison
class ShopRanking(BaseModel):
    shop: str
    avg_price: float
    min_price: float
    max_price: float
    product_count: int

class CategoryAnalytics(BaseModel):
    category: str
    cheapest_shop: str
    cheapest_avg_price: float
    shop_rankings: List[ShopRanking]
    only_available: bool
