from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class EnergyConsumption(BaseModel):
    daily_kwh: float
    monthly_kwh: float
    yearly_kwh: float


class EnergyCost(BaseModel):
    daily: float
    monthly: float
    yearly: float


class TotalCostOfOwnership(BaseModel):
    purchase_price: float
    five_year_energy_cost: float
    five_year_total: float


class EnergyCalculationResponse(BaseModel):
    product_id: str
    product_name: str
    category: str
    wattage: float
    usage_hours_per_day: float
    efficiency_rating: str
    efficiency_factor: float
    consumption: EnergyConsumption
    cost_tnd: EnergyCost
    total_cost_of_ownership: TotalCostOfOwnership
    co2_emissions_kg_per_year: float
    calculated_at: datetime


class EnergyCalculationRequest(BaseModel):
    product_id: str
    usage_hours_per_day: Optional[float] = None
    custom_wattage: Optional[float] = None


class EnergyCompareRequest(BaseModel):
    product_ids: List[str]


class EnergyComparisonItem(BaseModel):
    product_id: str
    product_name: str
    category: str
    wattage: float
    efficiency_rating: str
    efficiency_rank: int
    yearly_savings_vs_worst: float
    consumption: EnergyConsumption
    cost_tnd: EnergyCost
    total_cost_of_ownership: TotalCostOfOwnership
    co2_emissions_kg_per_year: float


class EnergyCompareResponse(BaseModel):
    comparison: List[EnergyComparisonItem]
    most_efficient: Optional[EnergyComparisonItem] = None
    least_efficient: Optional[EnergyComparisonItem] = None
    total_devices: int


class EnergySavingTipsResponse(BaseModel):
    category: str
    tips: List[str]


class EnergyCategoriesResponse(BaseModel):
    categories: Dict[str, Dict[str, Any]]
