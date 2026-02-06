from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.db.mongodb import db
from bson import ObjectId

router = APIRouter()

# Shop lists for each database
PARA_SHOPS = ["parashop", "pharma-shop", "parafendri"]
RETAIL_SHOPS = ["mytek", "tunisianet", "spacenet"]


class BagItem(BaseModel):
    sku: str  # This is actually the MongoDB ObjectId string
    source: str  # "para" or "retail"


class BagRequest(BaseModel):
    items: List[BagItem]


class ProductInShop(BaseModel):
    sku: str
    title: str
    image: Optional[str]
    price: Optional[float]
    available: bool


class ShopTotal(BaseModel):
    shop: str
    total: float
    products: List[ProductInShop]
    available_count: int
    missing_count: int


class CategoryResult(BaseModel):
    category: str  # "para" or "retail"
    category_label: str  # "Parapharmacie" or "Électronique"
    best_shop: Optional[str]
    best_total: Optional[float]
    shop_totals: List[ShopTotal]
    products: List[dict]


class BestShopResponse(BaseModel):
    para_result: Optional[CategoryResult]
    retail_result: Optional[CategoryResult]


def get_para_database():
    return db.client["PARA"]


def get_retail_database():
    return db.client["Retails"]


def calculate_shop_totals_for_products(products: List[dict], shop_list: List[str]) -> tuple:
    """Calculate shop totals for a list of products within specified shops."""
    shop_totals = []
    
    for shop in shop_list:
        total = 0.0
        products_in_shop = []
        available_count = 0
        missing_count = 0

        for product in products:
            shops_data = product.get("shops", {})
            # Try different variations of shop name
            shop_data = shops_data.get(shop) or shops_data.get(shop.replace("-", "_")) or shops_data.get(shop.replace("_", "-"))
            
            if shop_data and shop_data.get("price") is not None:
                price = float(shop_data["price"])
                available = shop_data.get("available", True)
                
                # Get first image
                images = shop_data.get("images", [])
                image = images[0] if images else None
                
                products_in_shop.append(ProductInShop(
                    sku=product["sku"],
                    title=product["title"],
                    image=image,
                    price=price,
                    available=available
                ))
                
                if available:
                    total += price
                    available_count += 1
                else:
                    missing_count += 1
            else:
                # Product not available in this shop
                missing_count += 1
                products_in_shop.append(ProductInShop(
                    sku=product["sku"],
                    title=product["title"],
                    image=None,
                    price=None,
                    available=False
                ))

        if available_count > 0:  # Only include shops that have at least one product
            shop_totals.append(ShopTotal(
                shop=shop,
                total=round(total, 3),
                products=products_in_shop,
                available_count=available_count,
                missing_count=missing_count
            ))

    # Sort by total price (lowest first), but prioritize shops with all items available
    shop_totals.sort(key=lambda x: (x.missing_count, x.total))

    # Determine best shop
    best_shop = None
    best_total = None
    
    for st in shop_totals:
        if st.missing_count == 0 and st.available_count > 0:
            best_shop = st.shop
            best_total = st.total
            break
    
    # If no shop has all items, pick the one with most items and lowest price
    if best_shop is None and shop_totals:
        best_shop = shop_totals[0].shop
        best_total = shop_totals[0].total

    return shop_totals, best_shop, best_total


@router.post("/best-shop", response_model=BestShopResponse)
async def calculate_best_shop(request: BagRequest):
    """
    Calculate the best shop for para and retail products separately.
    Returns price breakdown per shop category.
    """
    if not request.items:
        raise HTTPException(status_code=400, detail="No items provided")

    # Separate items by source
    para_ids = []
    retail_ids = []
    
    for item in request.items:
        try:
            obj_id = ObjectId(item.sku)
            if item.source == "para":
                para_ids.append(obj_id)
            else:
                retail_ids.append(obj_id)
        except Exception as e:
            print(f"Invalid ObjectId: {item.sku}, error: {e}")
            continue

    para_products = []
    retail_products = []

    # Fetch PARA products by _id
    if para_ids:
        para_db = get_para_database()
        para_collection = para_db["merged_products"]
        para_docs = await para_collection.find({"_id": {"$in": para_ids}}).to_list(length=None)
        for doc in para_docs:
            para_products.append({
                "sku": str(doc.get("_id")),
                "title": doc.get("title", "Unknown"),
                "shops": doc.get("shops", {}),
                "source": "para"
            })

    # Fetch Retail products by _id
    if retail_ids:
        retail_db = get_retail_database()
        retail_collection = retail_db["merged_products"]
        retail_docs = await retail_collection.find({"_id": {"$in": retail_ids}}).to_list(length=None)
        for doc in retail_docs:
            retail_products.append({
                "sku": str(doc.get("_id")),
                "title": doc.get("title", "Unknown"),
                "shops": doc.get("shops", {}),
                "source": "retail"
            })

    # Calculate results for each category
    para_result = None
    retail_result = None

    if para_products:
        shop_totals, best_shop, best_total = calculate_shop_totals_for_products(para_products, PARA_SHOPS)
        para_result = CategoryResult(
            category="para",
            category_label="Parapharmacie",
            best_shop=best_shop,
            best_total=best_total,
            shop_totals=shop_totals,
            products=[{"sku": p["sku"], "title": p["title"]} for p in para_products]
        )

    if retail_products:
        shop_totals, best_shop, best_total = calculate_shop_totals_for_products(retail_products, RETAIL_SHOPS)
        retail_result = CategoryResult(
            category="retail",
            category_label="Électronique",
            best_shop=best_shop,
            best_total=best_total,
            shop_totals=shop_totals,
            products=[{"sku": p["sku"], "title": p["title"]} for p in retail_products]
        )

    return BestShopResponse(
        para_result=para_result,
        retail_result=retail_result
    )
