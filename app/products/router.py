from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional
from app.products import service, schemas

router = APIRouter()

@router.get("/random", response_model=List[schemas.Product])
async def read_random_products(
    category: str = Query(..., description="Category value to filter products"),
    category_type: str = Query("subcategory", description="Category field: 'subcategory' or 'low_category'"),
    limit: int = Query(10, description="Number of products to return (max 10)")
):
    """Get random products by category (subcategory or low_category)"""
    try:
        products = await service.get_random_products(
            category=category, 
            category_type=category_type,
            limit=limit
        )
        return products
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/by-sku/{sku}", response_model=schemas.Product)
async def get_product_by_sku(sku: str):
    """Get a single product by SKU with full specifications"""
    try:
        product = await service.get_product_by_sku(sku)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        return product
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/categories", response_model=List[str])
async def read_categories():
    """Get all distinct subcategories from merged_products"""
    try:
        categories = await service.get_categories()
        return categories
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/low-categories", response_model=List[str])
async def read_low_categories():
    """Get all distinct low_categories from merged_products"""
    try:
        categories = await service.get_all_low_categories()
        return categories
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search", response_model=List[schemas.SearchResult])
async def search_products(
    q: str = Query(..., description="Search query (name or SKU)"),
    limit: int = Query(10, description="Maximum number of results"),
    shop: Optional[str] = Query(None, description="Filter by shop name")
):
    """Search products by name or SKU for autocomplete, optionally filtered by shop"""
    try:
        if len(q) < 2:
            return []
        results = await service.search_products(q, limit, shop)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/listing", response_model=schemas.ProductListResponse)
async def get_products_listing(
    category: Optional[str] = Query(None, description="Category to filter by"),
    category_type: str = Query("subcategory", description="Category field: 'subcategory' or 'low_category'"),
    search: Optional[str] = Query(None, description="Search term"),
    min_price: Optional[float] = Query(None, description="Minimum price filter"),
    max_price: Optional[float] = Query(None, description="Maximum price filter"),
    in_stock: bool = Query(False, description="Filter for in-stock items only"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Products per page")
):
    """Get paginated product listing with filters"""
    try:
        result = await service.get_products_listing(
            category=category,
            category_type=category_type,
            search=search,
            min_price=min_price,
            max_price=max_price,
            in_stock_only=in_stock,
            page=page,
            limit=limit
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/categories", response_model=List[str])
async def get_analytics_categories():
    """Get all distinct categories from analytics_cheapest_by_category for Retails"""
    try:
        categories = await service.get_analytics_categories()
        return categories
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/by-category", response_model=schemas.CategoryAnalytics)
async def get_category_analytics(
    category: str = Query(..., description="Category name to get analytics for")
):
    """Get shop rankings and analytics for a specific category from Retails"""
    try:
        analytics = await service.get_category_analytics(category)
        if not analytics:
            raise HTTPException(status_code=404, detail=f"No analytics found for category: {category}")
        return analytics
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{product_id}", response_model=schemas.Product)
async def get_product_by_id(product_id: str):
    """Get a single product by ID with full specifications"""
    try:
        product = await service.get_product_by_id(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        return product
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
