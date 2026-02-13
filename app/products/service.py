from app.db.mongodb import get_database
from typing import List, Optional, Dict, Any, Tuple
from app.products.schemas import Product, ShopPrice, ProductListResponse, SearchResult, ShopRanking, CategoryAnalytics
import re

async def get_categories() -> List[str]:
    """Fetch distinct subcategories from merged_products collection"""
    db = get_database()
    client = db.client
    
    try:
        categories = await client["Retails"]["merged_products"].distinct("subcategory")
        return sorted([c for c in categories if c])
    except Exception as e:
        print(f"Error fetching categories: {e}")
        return []


def parse_product(p: dict, default_category: str = "", include_specs: bool = False) -> Product:
    """Parse a raw product document into a Product schema"""
    shops_data = p.get("shops", {})
    shop_prices = []
    specifications = None
    
    # Collect prices from ALL shops found in the document (fully dynamic)
    for shop_name, shop in shops_data.items():
        if shop and isinstance(shop, dict) and shop.get("price"):
            price = float(shop["price"])
            shop_prices.append(ShopPrice(
                shop=shop_name.capitalize(),
                price=price,
                oldPrice=float(shop["old_price"]) if shop.get("old_price") else None,
                available=bool(shop.get("available", False)),
                url=shop.get("url")
            ))
    
    # Sort by price (lowest first) - this ensures best price shop is first
    shop_prices.sort(key=lambda x: x.price)
    
    # Best price is the first one after sorting
    best_price = shop_prices[0].price if shop_prices else 0.0
    
    # Get original price from old_price if available
    old_prices = [sp.oldPrice for sp in shop_prices if sp.oldPrice]
    original_price = min(old_prices) if old_prices else None
    
    # Get first available image (skip spacenet livraison image)
    image_url = "/placeholder.svg"
    for shop_name, shop in shops_data.items():
        if shop and isinstance(shop, dict) and shop.get("images") and len(shop["images"]) > 0:
            for img in shop["images"]:
                # Skip spacenet livraison image
                if "livraison-gratuite" not in img:
                    image_url = img
                    break
            if image_url != "/placeholder.svg":
                break
    
    # Get brand from first shop that has it
    brand = "Generic"
    for shop_name, shop in shops_data.items():
        if shop and isinstance(shop, dict) and shop.get("brand"):
            brand = shop["brand"].upper()
            break
    
    # Check availability across shops
    in_stock = any(sp.available for sp in shop_prices)
    
    # Get product _id as ID
    product_id = str(p.get("_id", "unknown"))
    
    # Get specifications if requested
    if include_specs:
        specifications = {}
        for shop_name, shop in shops_data.items():
            if shop and isinstance(shop, dict) and shop.get("specifications"):
                # Merge specifications from all shops
                for key, value in shop["specifications"].items():
                    if key not in specifications:
                        specifications[key] = value
    
    return Product(
        id=product_id,
        name=p.get("title", "Unknown Product"),
        brand=brand,
        bestPrice=best_price,
        originalPrice=float(original_price) if original_price else None,
        image=image_url,
        description=p.get("title", ""),
        inStock=in_stock,
        category=p.get("subcategory") or p.get("low_category") or default_category,
        shopPrices=shop_prices,
        specifications=specifications
    )


def parse_single_shop_product(p: dict, shop_name: str) -> Product:
    """Parse a single-shop product document into a Product schema"""
    price = float(p.get("price", 0))
    old_price = float(p["old_price"]) if p.get("old_price") else None
    
    shop_prices = [ShopPrice(
        shop=shop_name.capitalize(),
        price=price,
        oldPrice=old_price,
        available=bool(p.get("available", False)),
        url=p.get("url")
    )]
    
    # Get first image (skip spacenet livraison image)
    image_url = "/placeholder.svg"
    images = p.get("images", [])
    for img in images:
        if "livraison-gratuite" not in img:
            image_url = img
            break
    
    brand = p.get("brand", "Generic")
    if brand:
        brand = brand.upper()
    
    return Product(
        id=str(p.get("_id", "unknown")),
        name=p.get("title", "Unknown Product"),
        brand=brand,
        bestPrice=price,
        originalPrice=old_price,
        image=image_url,
        description=p.get("overview", p.get("title", "")),
        inStock=bool(p.get("available", False)),
        category=p.get("subcategory") or p.get("low_category"),
        shopPrices=shop_prices,
        specifications=p.get("specifications")
    )


async def get_random_products(category: str, category_type: str = "subcategory", limit: int = 10) -> List[Product]:
    """Fetch random products from merged_products by subcategory or low_category"""
    db = get_database()
    client = db.client
    collection = client["Retails"]["merged_products"]
    
    # Build aggregation pipeline - limit to max 10
    actual_limit = min(limit, 10)
    
    # Match by either subcategory or low_category
    match_field = category_type if category_type in ["subcategory", "low_category"] else "subcategory"
    
    pipeline = [
        {"$match": {match_field: category}},
        {"$sample": {"size": actual_limit}}
    ]
    
    cursor = collection.aggregate(pipeline)
    raw_products = await cursor.to_list(length=actual_limit)
    
    # Map to Product schema
    products = [parse_product(p, category) for p in raw_products]
    
    return products


async def get_product_by_id(product_id: str) -> Optional[Product]:
    """Fetch a single product by its MongoDB ID with full specifications"""
    from bson import ObjectId
    try:
        obj_id = ObjectId(product_id)
    except:
        return None
        
    db = get_database()
    client = db.client
    
    # First try merged_products
    collection = client["Retails"]["merged_products"]
    product_doc = await collection.find_one({"_id": obj_id})
    
    if product_doc:
        return parse_product(product_doc, include_specs=True)
    
    # If not found, try individual shop collections
    for shop_name, collection_name in [
        ("mytek", "mytek_details"),
        ("spacenet", "spacenet_details"),
        ("tunisianet", "tunisianet_details"),
        ("technopro", "technopro_details"),
        ("darty", "darty_details")
    ]:
        collection = client["Retails"][collection_name]
        product_doc = await collection.find_one({"_id": obj_id})
        if product_doc:
            return parse_single_shop_product(product_doc, shop_name)
    
    return None


async def get_product_by_sku(sku: str) -> Optional[Product]:
    """Fetch a single product by its SKU with full specifications"""
    db = get_database()
    client = db.client
    
    # First try merged_products
    collection = client["Retails"]["merged_products"]
    product_doc = await collection.find_one({"sku": sku})
    
    if product_doc:
        return parse_product(product_doc, include_specs=True)
    
    # If not found, try individual shop collections
    for shop_name, collection_name in [
        ("mytek", "mytek_details"),
        ("spacenet", "spacenet_details"),
        ("tunisianet", "tunisianet_details"),
        ("technopro", "technopro_details"),
        ("darty", "darty_details")
    ]:
        collection = client["Retails"][collection_name]
        product_doc = await collection.find_one({"sku": sku})
        if product_doc:
            return parse_single_shop_product(product_doc, shop_name)
    
    return None


async def search_products(query: str, limit: int = 10, shop: Optional[str] = None) -> List[SearchResult]:
    """Search products by name or SKU for autocomplete, optionally filtered by shop"""
    db = get_database()
    client = db.client
    
    results = []
    seen_skus = set()
    
    # Create regex pattern for case-insensitive search
    regex_pattern = {"$regex": query, "$options": "i"}
    
    # Search merged_products first (priority)
    collection = client["Retails"]["merged_products"]
    
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
            product = parse_product(p)
            
            # If filtering by shop, use that shop's price
            price = product.bestPrice
            if shop and p.get("shops") and p["shops"].get(shop) and p["shops"][shop].get("price"):
                try:
                    price = float(p["shops"][shop]["price"])
                except:
                    pass
            
            results.append(SearchResult(
                id=product.id,
                name=product.name,
                brand=product.brand,
                bestPrice=price,
                image=product.image,
                inStock=product.inStock
            ))
    
    # If we need more results, search individual shop collections
    if len(results) < limit:
        remaining = limit - len(results)
        
        shop_collections = [
            ("mytek", "mytek_details"),
            ("spacenet", "spacenet_details"),
            ("tunisianet", "tunisianet_details"),
            ("technopro", "technopro_details"),
            ("darty", "darty_details")
        ]
        
        # If shop filter is active, only search that shop's collection
        if shop:
            shop_collections = [s for s in shop_collections if s[0] == shop]

        for shop_name, collection_name in shop_collections:
            if len(results) >= limit:
                break
            
            collection = client["Retails"][collection_name]
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
                    product = parse_single_shop_product(p, shop_name)
                    results.append(SearchResult(
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


async def get_products_listing(
    category: Optional[str] = None,
    category_type: str = "subcategory",
    search: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock_only: bool = False,
    page: int = 1,
    limit: int = 20
) -> ProductListResponse:
    """Get paginated product listing with filters using Aggregation Pipeline"""
    db = get_database()
    client = db.client
    collection = client["Retails"]["merged_products"]
    
    # 1. Base Match Stage
    match_stage = {}
    if category:
        match_field = category_type if category_type in ["subcategory", "low_category"] else "subcategory"
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
        products = [parse_product(p) for p in products_raw]
        
        return ProductListResponse(
            products=products,
            total=total,
            page=page,
            limit=limit,
            totalPages=total_pages
        )
        
    except Exception as e:
        print(f"Aggregation Error: {e}")
        # Fallback to empty response on error
        return ProductListResponse(
            products=[],
            total=0,
            page=page,
            limit=limit,
            totalPages=0
        )


async def get_all_low_categories() -> List[str]:
    """Fetch distinct low_categories from merged_products collection"""
    db = get_database()
    client = db.client
    
    try:
        categories = await client["Retails"]["merged_products"].distinct("low_category")
        return sorted([c for c in categories if c])
    except Exception as e:
        print(f"Error fetching low_categories: {e}")
        return []


async def get_analytics_categories() -> List[str]:
    """Get all distinct categories from analytics_cheapest_by_category collection for Retails"""
    db = get_database()
    client = db.client
    
    try:
        categories = await client["Retails"]["analytics_cheapest_by_category"].distinct("category")
        return sorted(categories) if categories else []
    except Exception as e:
        print(f"Error fetching analytics categories: {e}")
        return []


async def get_category_analytics(category: str) -> Optional[CategoryAnalytics]:
    """Get analytics data for a specific category from Retails database"""
    db = get_database()
    client = db.client
    
    try:
        doc = await client["Retails"]["analytics_cheapest_by_category"].find_one({"category": category})
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
