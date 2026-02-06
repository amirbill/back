from app.db.mongodb import db
from typing import List, Optional, Dict, Any
from app.para.schemas import ParaProduct, ShopPrice, ParaProductListResponse, ParaSearchResult, ShopRanking, CategoryAnalytics

# PARA shops list
PARA_SHOPS = ["parashop", "pharma-shop", "parafendri"]

def get_para_database():
    """Get the PARA database"""
    return db.client["PARA"]


def parse_para_product(p: dict, default_category: str = "", include_specs: bool = False) -> ParaProduct:
    """Parse a raw PARA product document into a ParaProduct schema"""
    shops_data = p.get("shops", {})
    shop_prices = []
    specifications = None
    
    # Collect prices from all PARA shops
    for shop_name in PARA_SHOPS:
        shop = shops_data.get(shop_name)
        if shop and shop.get("price"):
            price = float(shop["price"])
            shop_prices.append(ShopPrice(
                shop=shop_name.replace("-", " ").title(),
                price=round(price, 3),
                oldPrice=float(shop["old_price"]) if shop.get("old_price") else None,
                available=bool(shop.get("available", False)),
                url=shop.get("url")
            ))
    
    # Sort by price (lowest first)
    shop_prices.sort(key=lambda x: x.price)
    
    # Best price is the first one after sorting
    best_price = shop_prices[0].price if shop_prices else 0.0
    
    # Get original price from old_price if available
    old_prices = [sp.oldPrice for sp in shop_prices if sp.oldPrice]
    original_price = min(old_prices) if old_prices else None
    
    # Get first available image
    image_url = "/placeholder.svg"
    for shop_name in PARA_SHOPS:
        shop = shops_data.get(shop_name)
        if shop and shop.get("images") and len(shop["images"]) > 0:
            image_url = shop["images"][0]
            break
    
    # Get brand from first shop
    brand = "Generic"
    for shop_name in PARA_SHOPS:
        shop = shops_data.get(shop_name)
        if shop and shop.get("brand"):
            brand = shop["brand"].upper()
            break
    
    # Check availability across shops
    in_stock = any(sp.available for sp in shop_prices)
    
    # Get product _id as ID
    product_id = str(p.get("_id", "unknown"))
    
    # Get specifications if requested
    if include_specs:
        specifications = {}
        for shop_name in PARA_SHOPS:
            shop = shops_data.get(shop_name)
            if shop and shop.get("specifications"):
                for key, value in shop["specifications"].items():
                    if key not in specifications:
                        specifications[key] = value
    
    return ParaProduct(
        id=product_id,
        name=p.get("title", "Unknown Product"),
        brand=brand,
        bestPrice=round(best_price, 3),
        originalPrice=round(float(original_price), 3) if original_price else None,
        image=image_url,
        description=p.get("title", ""),
        inStock=in_stock,
        category=p.get("low_category") or p.get("subcategory") or default_category,
        topCategory=p.get("top_category"),
        shopPrices=shop_prices,
        specifications=specifications
    )


def parse_single_para_shop_product(p: dict, shop_name: str) -> ParaProduct:
    """Parse a single-shop PARA product document"""
    price = float(p.get("price", 0))
    old_price = float(p["old_price"]) if p.get("old_price") else None
    
    shop_prices = [ShopPrice(
        shop=shop_name.replace("-", " ").title(),
        price=round(price, 3),
        oldPrice=round(old_price, 3) if old_price else None,
        available=bool(p.get("available", False)),
        url=p.get("url")
    )]
    
    # Get first image
    image_url = "/placeholder.svg"
    images = p.get("images", [])
    if images:
        image_url = images[0]
    
    brand = p.get("brand", "Generic")
    if brand:
        brand = brand.upper()
    
    return ParaProduct(
        id=str(p.get("_id", "unknown")),
        name=p.get("title", "Unknown Product"),
        brand=brand,
        bestPrice=round(price, 3),
        originalPrice=round(old_price, 3) if old_price else None,
        image=image_url,
        description=p.get("description", p.get("title", "")),
        inStock=bool(p.get("available", False)),
        category=p.get("low_category") or p.get("subcategory"),
        topCategory=p.get("top_category"),
        shopPrices=shop_prices,
        specifications={}
    )


def get_category_field(category_type: str) -> str:
    """Map category type to actual field name"""
    mapping = {
        "top": "top_category",
        "low": "low_category",
        "top_category": "top_category",
        "low_category": "low_category",
        "subcategory": "subcategory"
    }
    return mapping.get(category_type, "top_category")


async def get_para_categories(category_type: str = "top_category") -> List[str]:
    """Fetch distinct categories from PARA merged_products collection"""
    para_db = get_para_database()
    field = get_category_field(category_type)
    
    try:
        categories = await para_db["merged_products"].distinct(field)
        return sorted([c for c in categories if c])
    except Exception as e:
        print(f"Error fetching PARA categories: {e}")
        return []


async def get_para_random_products(
    category: str, 
    category_type: str = "top_category", 
    limit: int = 10
) -> List[ParaProduct]:
    """Fetch random PARA products by category"""
    para_db = get_para_database()
    collection = para_db["merged_products"]
    
    actual_limit = min(limit, 10)
    match_field = get_category_field(category_type)
    
    pipeline = [
        {"$match": {match_field: category}},
        {"$sample": {"size": actual_limit}}
    ]
    
    cursor = collection.aggregate(pipeline)
    raw_products = await cursor.to_list(length=actual_limit)
    
    products = [parse_para_product(p, category) for p in raw_products]
    
    return products


async def get_para_product_by_id(product_id: str) -> Optional[ParaProduct]:
    """Fetch a single PARA product by MongoDB ID"""
    from bson import ObjectId
    try:
        obj_id = ObjectId(product_id)
    except:
        return None
        
    para_db = get_para_database()
    
    # First try merged_products
    collection = para_db["merged_products"]
    product_doc = await collection.find_one({"_id": obj_id})
    
    if product_doc:
        return parse_para_product(product_doc, include_specs=True)
    
    # If not found, try individual shop collections
    for shop_name in ["parashop_details", "pharma-shop_details", "parafendri_details"]:
        collection = para_db[shop_name]
        product_doc = await collection.find_one({"_id": obj_id})
        if product_doc:
            shop = shop_name.replace("_details", "")
            return parse_single_para_shop_product(product_doc, shop)
    
    return None


async def get_para_product_by_sku(sku: str) -> Optional[ParaProduct]:
    """Fetch a single PARA product by SKU"""
    para_db = get_para_database()
    
    # First try merged_products
    collection = para_db["merged_products"]
    product_doc = await collection.find_one({"sku": sku})
    
    if product_doc:
        return parse_para_product(product_doc, include_specs=True)
    
    # If not found, try individual shop collections
    for shop_name in ["parashop_details", "pharma-shop_details", "parafendri_details"]:
        collection = para_db[shop_name]
        product_doc = await collection.find_one({"sku": sku})
        if product_doc:
            shop = shop_name.replace("_details", "")
            return parse_single_para_shop_product(product_doc, shop)
    
    return None


async def search_para_products(query: str, limit: int = 10, shop: Optional[str] = None) -> List[ParaSearchResult]:
    """Search PARA products by name or SKU for autocomplete, optionally filtered by shop"""
    para_db = get_para_database()
    
    results = []
    seen_skus = set()
    
    regex_pattern = {"$regex": query, "$options": "i"}
    
    # Search merged_products first
    collection = para_db["merged_products"]
    
    match_query = {
        "$or": [
            {"title": regex_pattern},
            {"sku": regex_pattern}
        ]
    }
    
    if shop:
        match_query[f"shops.{shop}"] = {"$exists": True}

    cursor = collection.find(match_query).limit(limit)
    
    async for p in cursor:
        sku = p.get("sku")
        if sku and sku not in seen_skus:
            seen_skus.add(sku)
            product = parse_para_product(p)
            
            # If filtering by shop, use that shop's price
            price = product.bestPrice
            if shop and p.get("shops") and p["shops"].get(shop) and p["shops"][shop].get("price"):
                try:
                    price = float(p["shops"][shop]["price"])
                except:
                    pass
            
            results.append(ParaSearchResult(
                id=product.id,
                name=product.name,
                brand=product.brand,
                bestPrice=price,
                image=product.image,
                inStock=product.inStock
            ))
    
    # Search individual shop collections if needed
    if len(results) < limit:
        remaining = limit - len(results)
        
        shop_collections = ["parashop_details", "pharma-shop_details", "parafendri_details"]
        
        # If shop filter is active, only search that shop's collection (by checking if collection name starts with shop)
        if shop:
            # e.g. shop='parashop' matches 'parashop_details'
            shop_collections = [s for s in shop_collections if s.startswith(shop)]
            
        for shop_collection in shop_collections:
            if len(results) >= limit:
                break
            
            collection = para_db[shop_collection]
            cursor = collection.find({
                "$or": [
                    {"title": regex_pattern},
                    {"sku": regex_pattern}
                ]
            }).limit(remaining)
            
            async for p in cursor:
                sku = p.get("sku")
                if sku and sku not in seen_skus:
                    seen_skus.add(sku)
                    shop_name = shop_collection.replace("_details", "")
                    product = parse_single_para_shop_product(p, shop_name)
                    results.append(ParaSearchResult(
                        id=product.id,
                        name=product.name,
                        brand=product.brand,
                        bestPrice=product.bestPrice,
                        image=product.image,
                        inStock=product.inStock
                    ))
                    if len(results) >= limit:
                        break
    
    return results[:limit]


async def get_para_products_listing(
    category: Optional[str] = None,
    category_type: str = "top_category",
    search: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock_only: bool = False,
    page: int = 1,
    limit: int = 20
) -> ParaProductListResponse:
    """Get paginated PARA product listing with filters using Aggregation Pipeline"""
    para_db = get_para_database()
    collection = para_db["merged_products"]
    
    # 1. Base Match Stage
    match_stage = {}
    if category:
        match_field = get_category_field(category_type)
        match_stage[match_field] = category
    
    if search:
        regex_pattern = {"$regex": search, "$options": "i"}
        match_stage["$or"] = [
            {"title": regex_pattern},
            {"sku": regex_pattern}
        ]

    pipeline = [{"$match": match_stage}]

    # 2. Add Computed Fields Stage (Price & Stock)
    # We convert 'shops' object to array to iterate and calculate derived fields
    pipeline.append({
        "$addFields": {
            "shops_array": {"$objectToArray": "$shops"}
        }
    })

    # Extract prices and availability
    pipeline.append({
        "$addFields": {
            "derived_best_price": {
                "$min": {
                    "$map": {
                        "input": "$shops_array",
                        "as": "shop",
                        "in": { 
                            "$convert": { 
                                "input": "$$shop.v.price", 
                                "to": "double", 
                                "onError": 9999999, 
                                "onNull": 9999999 
                            } 
                        } 
                    }
                }
            },
            "derived_in_stock": {
                "$anyElementTrue": {
                    "$map": {
                        "input": "$shops_array",
                        "as": "shop",
                        "in": "$$shop.v.available"
                    }
                }
            }
        }
    })
    
    # Handle cases where derived_best_price might be null (no shops) -> distinct from 0 to avoid false positives in cheap filters
    # If no valid price found (9999999), set to 0 or keep as is? 
    # Actually if we filter for < 20, keeping 9999999 ensures products with NO price don't show up.
    # But if we want to be safe, let's keep it high so it fails "max_price" filters but might pass "min_price".

    # 3. Filter Stage (Price & Stock)
    filter_stage = {}
    if min_price is not None:
        filter_stage["derived_best_price"] = {"$gte": min_price}
    
    if max_price is not None:
        if "derived_best_price" in filter_stage:
            filter_stage["derived_best_price"]["$lte"] = max_price
        else:
            filter_stage["derived_best_price"] = {"$lte": max_price}
            
    if in_stock_only:
        filter_stage["derived_in_stock"] = True

    if filter_stage:
        pipeline.append({"$match": filter_stage})

    # 4. Facet Stage (Pagination & Counting)
    skip = (page - 1) * limit
    pipeline.append({
        "$facet": {
            "metadata": [{"$count": "total"}],
            "products": [{"$skip": skip}, {"$limit": limit}]
        }
    })

    # Execute Aggregation
    try:
        result_list = await collection.aggregate(pipeline).to_list(length=1)
        # Result list will always have 1 element due to $facet
        result = result_list[0]
        
        metadata = result.get("metadata", [])
        products_raw = result.get("products", [])
        
        total = metadata[0]["total"] if metadata else 0
        total_pages = (total + limit - 1) // limit if total > 0 else 1
        
        # Parse products
        products = [parse_para_product(p) for p in products_raw]
        
        return ParaProductListResponse(
            products=products,
            total=total,
            page=page,
            limit=limit,
            totalPages=total_pages
        )
        
    except Exception as e:
        print(f"Aggregation Error: {e}")
        # Fallback to empty response on error
        return ParaProductListResponse(
            products=[],
            total=0,
            page=page,
            limit=limit,
            totalPages=0
        )


async def get_analytics_categories() -> List[str]:
    """Get all distinct categories from analytics_cheapest_by_category collection"""
    para_db = get_para_database()
    collection = para_db["analytics_cheapest_by_category"]
    
    try:
        categories = await collection.distinct("category")
        return sorted(categories) if categories else []
    except Exception as e:
        print(f"Error fetching analytics categories: {e}")
        return []


async def get_category_analytics(category: str) -> Optional[CategoryAnalytics]:
    """Get analytics data for a specific category"""
    para_db = get_para_database()
    collection = para_db["analytics_cheapest_by_category"]
    
    try:
        doc = await collection.find_one({"category": category})
        if not doc:
            return None
        
        shop_rankings = [
            ShopRanking(
                shop=r.get("shop", ""),
                avg_price=round(r.get("avg_price", 0), 2),
                min_price=round(r.get("min_price", 0), 2),
                max_price=round(r.get("max_price", 0), 2),
                product_count=r.get("product_count", 0)
            )
            for r in doc.get("shop_rankings", [])
        ]
        
        return CategoryAnalytics(
            category=doc.get("category", ""),
            cheapest_shop=doc.get("cheapest_shop", ""),
            cheapest_avg_price=round(doc.get("cheapest_avg_price", 0), 2),
            shop_rankings=shop_rankings,
            only_available=doc.get("only_available", True)
        )
    except Exception as e:
        print(f"Error fetching category analytics: {e}")
        return None
