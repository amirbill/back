"""
Energy Consumption AI Router
API endpoints for energy calculations, comparisons, tips, and categories.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.ml.energy_service import (
    calculate_product_energy,
    compare_products,
    get_tips,
    get_all_categories,
)

router = APIRouter()


class EnergyCalculateRequest(BaseModel):
    product_id: str
    usage_hours_per_day: Optional[float] = None
    custom_wattage: Optional[float] = None


class EnergyCompareRequest(BaseModel):
    product_ids: List[str]


@router.get("/calculate")
async def calculate_energy_get(
    product_id: str = Query(..., description="Product ID"),
    usage_hours: Optional[float] = Query(None, description="Custom usage hours per day"),
    custom_wattage: Optional[float] = Query(None, description="Custom wattage override"),
):
    """Calculate energy consumption for a product (GET)"""
    result = await calculate_product_energy(product_id, usage_hours, custom_wattage)
    if not result:
        raise HTTPException(status_code=404, detail="Product not found")
    return result


@router.post("/calculate")
async def calculate_energy_post(request: EnergyCalculateRequest):
    """Calculate energy consumption for a product (POST)"""
    result = await calculate_product_energy(
        request.product_id,
        request.usage_hours_per_day,
        request.custom_wattage,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Product not found")
    return result


@router.post("/compare")
async def compare_energy(request: EnergyCompareRequest):
    """Compare energy consumption of multiple products"""
    if len(request.product_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 product IDs required")
    if len(request.product_ids) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 products can be compared")

    result = await compare_products(request.product_ids)
    if not result:
        raise HTTPException(status_code=404, detail="No valid products found")
    return result


@router.get("/tips/{category}")
async def energy_tips(category: str):
    """Get energy saving tips for a device category"""
    return get_tips(category)


@router.get("/categories")
async def energy_categories():
    """Get all supported device categories"""
    return get_all_categories()
