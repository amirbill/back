from fastapi import APIRouter
from app.api.v1.endpoints import health

from app.products.router import router as products_router
from app.analytics.router import router as analytics_router
from app.para.router import router as para_router

from app.api.endpoints import auth
from app.api.endpoints import bag

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(products_router, prefix="/products", tags=["products"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(para_router, prefix="/para", tags=["para"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(bag.router, prefix="/bag", tags=["bag"])

