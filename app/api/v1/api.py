from fastapi import APIRouter
from app.api.v1.endpoints import health

from app.products.router import router as products_router
from app.analytics.router import router as analytics_router
from app.para.router import router as para_router

from app.api.endpoints import auth
from app.api.endpoints import admin
from app.api.endpoints import bag
from app.api.endpoints import blogs
from app.ml.router import router as energy_router
from app.chat.router import router as chat_router

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(products_router, prefix="/products", tags=["products"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(para_router, prefix="/para", tags=["para"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(blogs.router, prefix="/blogs", tags=["blogs"])
api_router.include_router(bag.router, prefix="/bag", tags=["bag"])
api_router.include_router(energy_router, prefix="/energy", tags=["energy"])
api_router.include_router(chat_router, prefix="/chat", tags=["chat"])

