from fastapi import APIRouter, HTTPException
from typing import List
from app.analytics import service, schemas

router = APIRouter()

@router.get("/prices", response_model=List[schemas.ShopAnalytics])
async def read_shop_prices():
    try:
        shops = await service.get_shop_prices()
        return shops
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/merge-stats", response_model=schemas.MergeStatsResponse)
async def read_merge_stats():
    """Get merge statistics from PARA and Retails databases"""
    try:
        stats = await service.get_merge_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/shop-details", response_model=schemas.DetailedAnalyticsResponse)
async def read_detailed_shop_analytics():
    """Get detailed shop analytics from PARA and Retails databases"""
    try:
        analytics = await service.get_detailed_shop_analytics()
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/store-products-added/{shop}", response_model=schemas.StoreProductsAddedResponse)
async def read_store_products_added(shop: str, source: str = "retails", limit: int = 12):
    """Get products_added rows for a specific store from Retails or PARA"""
    try:
        products = await service.get_store_products_added(shop=shop, source=source, limit=limit)
        return products
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
