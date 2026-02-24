"""
Energy Consumption AI Service
Hybrid rule-based + ML approach for calculating device energy consumption.
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from bson import ObjectId

from app.db.mongodb import db

# ─── Constants ────────────────────────────────────────────────────────────────

ELECTRICITY_RATE_TND = 0.18  # Average Tunisia residential rate (TND/kWh)
CO2_PER_KWH = 0.5  # kg CO2 per kWh (Tunisia grid average)

# ─── Device Categories ────────────────────────────────────────────────────────

DEVICE_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "refrigerator": {
        "typical_wattage": 150,
        "usage_hours_per_day": 24,
        "efficiency_factor": 0.85,
        "standby_ratio": 0.3,
        "keywords": ["réfrigérateur", "refrigerateur", "frigo", "fridge", "refrigerator", "congélateur", "congelateur", "freezer"],
    },
    "air_conditioner": {
        "typical_wattage": 2000,
        "usage_hours_per_day": 8,
        "efficiency_factor": 0.90,
        "standby_ratio": 0.05,
        "keywords": ["climatiseur", "climatisation", "clim", "air conditioner", "ac", "split"],
    },
    "washing_machine": {
        "typical_wattage": 500,
        "usage_hours_per_day": 1,
        "efficiency_factor": 0.88,
        "standby_ratio": 0.02,
        "keywords": ["machine à laver", "machine a laver", "lave-linge", "lave linge", "washing machine"],
    },
    "dryer": {
        "typical_wattage": 3000,
        "usage_hours_per_day": 1,
        "efficiency_factor": 0.85,
        "standby_ratio": 0.02,
        "keywords": ["sèche-linge", "seche-linge", "seche linge", "dryer"],
    },
    "dishwasher": {
        "typical_wattage": 1800,
        "usage_hours_per_day": 1,
        "efficiency_factor": 0.87,
        "standby_ratio": 0.02,
        "keywords": ["lave-vaisselle", "lave vaisselle", "dishwasher"],
    },
    "television": {
        "typical_wattage": 100,
        "usage_hours_per_day": 5,
        "efficiency_factor": 0.92,
        "standby_ratio": 0.1,
        "keywords": ["télévision", "television", "tv", "téléviseur", "televiseur", "écran", "ecran", "smart tv", "led tv", "oled"],
    },
    "microwave": {
        "typical_wattage": 1000,
        "usage_hours_per_day": 0.5,
        "efficiency_factor": 0.95,
        "standby_ratio": 0.05,
        "keywords": ["micro-onde", "micro onde", "microwave", "four micro"],
    },
    "oven": {
        "typical_wattage": 2500,
        "usage_hours_per_day": 1,
        "efficiency_factor": 0.90,
        "standby_ratio": 0.02,
        "keywords": ["four", "oven", "cuisinière", "cuisiniere", "plaque de cuisson"],
    },
    "computer": {
        "typical_wattage": 300,
        "usage_hours_per_day": 8,
        "efficiency_factor": 0.90,
        "standby_ratio": 0.1,
        "keywords": ["ordinateur", "desktop", "pc", "computer", "workstation", "tour"],
    },
    "laptop": {
        "typical_wattage": 65,
        "usage_hours_per_day": 6,
        "efficiency_factor": 0.92,
        "standby_ratio": 0.05,
        "keywords": ["laptop", "pc portable", "ordinateur portable", "notebook", "ultrabook", "macbook"],
    },
    "water_heater": {
        "typical_wattage": 2000,
        "usage_hours_per_day": 3,
        "efficiency_factor": 0.85,
        "standby_ratio": 0.1,
        "keywords": ["chauffe-eau", "chauffe eau", "water heater", "chaudière", "chaudiere", "ballon d'eau"],
    },
    "fan": {
        "typical_wattage": 60,
        "usage_hours_per_day": 8,
        "efficiency_factor": 0.95,
        "standby_ratio": 0.0,
        "keywords": ["ventilateur", "fan", "brasseur"],
    },
    "vacuum_cleaner": {
        "typical_wattage": 1400,
        "usage_hours_per_day": 0.5,
        "efficiency_factor": 0.90,
        "standby_ratio": 0.0,
        "keywords": ["aspirateur", "vacuum", "cleaner"],
    },
    "iron": {
        "typical_wattage": 2000,
        "usage_hours_per_day": 0.5,
        "efficiency_factor": 0.95,
        "standby_ratio": 0.0,
        "keywords": ["fer à repasser", "fer a repasser", "iron", "repassage"],
    },
}

# ─── Efficiency Ratings ───────────────────────────────────────────────────────

EFFICIENCY_RATINGS: Dict[str, float] = {
    "A+++": 0.75,
    "A++": 0.81,
    "A+": 0.87,
    "A": 0.93,
    "B": 1.0,
    "C": 1.10,
    "D": 1.20,
    "E": 1.35,
    "F": 1.50,
    "G": 1.65,
}

# ─── Energy Saving Tips ──────────────────────────────────────────────────────

ENERGY_SAVING_TIPS: Dict[str, List[str]] = {
    "refrigerator": [
        "Réglez la température entre 3°C et 5°C pour une efficacité optimale",
        "Évitez d'ouvrir la porte fréquemment",
        "Laissez les aliments chauds refroidir avant de les mettre au réfrigérateur",
        "Nettoyez les serpentins de condensation régulièrement",
        "Vérifiez que les joints de porte sont bien étanches",
    ],
    "air_conditioner": [
        "Réglez la température entre 24°C et 26°C pour une efficacité optimale",
        "Nettoyez ou remplacez les filtres mensuellement",
        "Utilisez une minuterie ou un contrôle intelligent pour éviter un refroidissement inutile",
        "Assurez une bonne isolation de la pièce",
        "Utilisez des ventilateurs de plafond pour faire circuler l'air frais",
    ],
    "washing_machine": [
        "Lavez à l'eau froide quand c'est possible",
        "Remplissez la machine complètement avant de lancer un cycle",
        "Utilisez des programmes éco quand disponibles",
        "Nettoyez le filtre régulièrement",
        "Essorez à vitesse élevée pour réduire le temps de séchage",
    ],
    "dryer": [
        "Nettoyez le filtre à peluches après chaque utilisation",
        "Séchez les vêtements à l'air libre quand possible",
        "Ne surchargez pas le sèche-linge",
        "Utilisez le programme éco ou basse température",
        "Essorez bien les vêtements avant de les mettre au sèche-linge",
    ],
    "dishwasher": [
        "Remplissez complètement le lave-vaisselle avant de le lancer",
        "Utilisez le programme éco",
        "Évitez le pré-rinçage à l'eau chaude",
        "Laissez sécher la vaisselle à l'air libre plutôt qu'en utilisant le séchage chauffant",
        "Nettoyez les filtres régulièrement",
    ],
    "television": [
        "Réduisez la luminosité de l'écran",
        "Activez le mode économie d'énergie",
        "Éteignez complètement la TV plutôt que de la laisser en veille",
        "Utilisez une minuterie de mise en veille automatique",
        "Choisissez un écran LED plutôt qu'un plasma",
    ],
    "microwave": [
        "Utilisez des couvercles pour accélérer le chauffage",
        "Nettoyez l'intérieur régulièrement pour une efficacité maximale",
        "Dégivrez les aliments naturellement avant d'utiliser le micro-ondes",
        "Utilisez des récipients adaptés au micro-ondes",
        "Évitez de faire fonctionner le micro-ondes à vide",
    ],
    "oven": [
        "Préchauffez uniquement quand c'est nécessaire",
        "Utilisez la chaleur tournante pour une cuisson plus uniforme et rapide",
        "Évitez d'ouvrir la porte du four pendant la cuisson",
        "Utilisez des plats en verre ou en céramique (meilleure rétention de chaleur)",
        "Éteignez le four 5-10 minutes avant la fin de la cuisson",
    ],
    "computer": [
        "Activez le mode veille après 15 minutes d'inactivité",
        "Réduisez la luminosité de l'écran",
        "Éteignez l'ordinateur la nuit",
        "Utilisez un multiprise avec interrupteur pour couper complètement l'alimentation",
        "Choisissez une alimentation certifiée 80 PLUS",
    ],
    "laptop": [
        "Réduisez la luminosité de l'écran",
        "Débranchez le chargeur quand la batterie est pleine",
        "Fermez les applications inutilisées",
        "Activez le mode économie d'énergie",
        "Maintenez le système d'exploitation et les pilotes à jour",
    ],
    "water_heater": [
        "Réglez la température à 55-60°C",
        "Isolez les tuyaux d'eau chaude",
        "Utilisez une minuterie pour chauffer l'eau aux heures creuses",
        "Vidangez le chauffe-eau annuellement pour enlever le calcaire",
        "Envisagez un chauffe-eau solaire pour réduire la consommation",
    ],
    "fan": [
        "Utilisez la vitesse la plus basse confortable",
        "Éteignez quand vous quittez la pièce",
        "Nettoyez les pales régulièrement pour maintenir l'efficacité",
        "Positionnez le ventilateur pour optimiser la circulation d'air",
        "Utilisez en combinaison avec la climatisation pour économiser",
    ],
    "vacuum_cleaner": [
        "Videz ou changez le sac régulièrement",
        "Nettoyez les filtres pour maintenir l'aspiration",
        "Utilisez le mode éco pour les sols lisses",
        "Ramassez les gros débris avant d'aspirer",
        "Entretenez les brosses et accessoires",
    ],
    "iron": [
        "Repassez les vêtements délicats d'abord (température basse)",
        "Utilisez la vapeur de manière efficace",
        "Repassez plusieurs vêtements en une seule session",
        "Éteignez le fer quelques minutes avant de finir (chaleur résiduelle)",
        "Utilisez une table à repasser réfléchissante",
    ],
}


# ─── Helper Functions ─────────────────────────────────────────────────────────

def detect_category(name: str, description: str = "", category_hint: str = "") -> str:
    """Detect device category from product name/description"""
    text = f"{name} {description} {category_hint}".lower()

    for cat_key, cat_info in DEVICE_CATEGORIES.items():
        for keyword in cat_info["keywords"]:
            if keyword.lower() in text:
                return cat_key

    return "other"


def extract_wattage(specs: Optional[Dict[str, Any]], name: str = "") -> Optional[float]:
    """Extract power rating from specifications or product name"""
    if specs:
        # Look for power-related keys
        power_keys = ["puissance", "power", "wattage", "watts", "watt", "consumption", "consommation"]
        for key, value in specs.items():
            key_lower = key.lower()
            if any(pk in key_lower for pk in power_keys):
                # Extract numeric value
                if isinstance(value, (int, float)):
                    return float(value)
                if isinstance(value, str):
                    match = re.search(r'(\d+[\.,]?\d*)\s*(w|watt)', value.lower())
                    if match:
                        return float(match.group(1).replace(',', '.'))
                    # Try just a number
                    match = re.search(r'(\d+[\.,]?\d*)', value)
                    if match:
                        val = float(match.group(1).replace(',', '.'))
                        if 5 <= val <= 10000:  # Reasonable wattage range
                            return val

    # Try extracting from product name
    if name:
        match = re.search(r'(\d+)\s*[wW](?:att)?(?:s)?\b', name)
        if match:
            return float(match.group(1))

    return None


def detect_efficiency_rating(specs: Optional[Dict[str, Any]], name: str = "") -> str:
    """Detect energy efficiency rating from specs or name"""
    text = f"{name} {str(specs or '')}".upper()

    # Check for efficiency ratings (most specific first)
    for rating in ["A+++", "A++", "A+", "A", "B", "C", "D", "E", "F", "G"]:
        if rating in text:
            return rating

    if specs:
        efficiency_keys = ["classe", "class", "efficiency", "efficacité", "energy", "énergie"]
        for key, value in specs.items():
            if any(ek in key.lower() for ek in efficiency_keys):
                val = str(value).strip().upper()
                if val in EFFICIENCY_RATINGS:
                    return val

    return "B"  # Default


# ─── Core Calculation ─────────────────────────────────────────────────────────

def calculate_energy(
    wattage: float,
    usage_hours: float,
    efficiency_factor: float,
    standby_ratio: float = 0.05,
) -> Dict[str, float]:
    """Calculate energy consumption using physics-based formula"""
    # Active consumption
    active_kwh_daily = (wattage / 1000) * usage_hours * efficiency_factor

    # Standby consumption (remaining hours)
    standby_hours = 24 - usage_hours
    standby_kwh_daily = (wattage / 1000) * standby_ratio * standby_hours

    daily_kwh = round(active_kwh_daily + standby_kwh_daily, 3)
    monthly_kwh = round(daily_kwh * 30, 2)
    yearly_kwh = round(daily_kwh * 365, 2)

    return {
        "daily_kwh": daily_kwh,
        "monthly_kwh": monthly_kwh,
        "yearly_kwh": yearly_kwh,
    }


def calculate_cost(consumption: Dict[str, float]) -> Dict[str, float]:
    """Calculate energy cost in TND"""
    return {
        "daily": round(consumption["daily_kwh"] * ELECTRICITY_RATE_TND, 3),
        "monthly": round(consumption["monthly_kwh"] * ELECTRICITY_RATE_TND, 2),
        "yearly": round(consumption["yearly_kwh"] * ELECTRICITY_RATE_TND, 2),
    }


# ─── Main Service Functions ──────────────────────────────────────────────────

async def get_product_for_energy(product_id: str) -> Optional[Dict[str, Any]]:
    """Fetch product from either Retails or PARA database"""
    try:
        obj_id = ObjectId(product_id)
    except Exception:
        return None

    # Try Retails database first
    retails_db = db.client["Retails"]
    product = await retails_db["merged_products"].find_one({"_id": obj_id})
    if product:
        product["_source"] = "retails"
        return product

    # Try PARA database
    para_db = db.client["PARA"]
    product = await para_db["merged_products"].find_one({"_id": obj_id})
    if product:
        product["_source"] = "para"
        return product

    return None


async def calculate_product_energy(
    product_id: str,
    usage_hours_per_day: Optional[float] = None,
    custom_wattage: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Calculate energy consumption for a product"""
    product = await get_product_for_energy(product_id)
    if not product:
        return None

    # Extract product info
    name = product.get("title", product.get("name", "Unknown"))
    description = product.get("description", "")
    category_hint = product.get("subcategory", product.get("low_category", product.get("top_category", "")))
    specs = product.get("specifications", {})

    # Detect category
    category = detect_category(name, description, category_hint)
    cat_config = DEVICE_CATEGORIES.get(category, {
        "typical_wattage": 200,
        "usage_hours_per_day": 4,
        "efficiency_factor": 0.90,
        "standby_ratio": 0.05,
    })

    # Determine wattage
    wattage = custom_wattage or extract_wattage(specs, name) or cat_config["typical_wattage"]

    # Determine usage hours
    usage_hours = usage_hours_per_day or cat_config["usage_hours_per_day"]

    # Detect efficiency rating
    efficiency_rating = detect_efficiency_rating(specs, name)
    efficiency_multiplier = EFFICIENCY_RATINGS.get(efficiency_rating, 1.0)
    efficiency_factor = cat_config["efficiency_factor"] * efficiency_multiplier

    # Calculate consumption
    consumption = calculate_energy(
        wattage=wattage,
        usage_hours=usage_hours,
        efficiency_factor=efficiency_factor,
        standby_ratio=cat_config["standby_ratio"],
    )

    # Calculate cost
    cost = calculate_cost(consumption)

    # Get purchase price
    purchase_price = 0.0
    shops = product.get("shops", {})
    prices = []
    for shop_data in shops.values():
        if isinstance(shop_data, dict) and shop_data.get("price"):
            try:
                prices.append(float(shop_data["price"]))
            except (ValueError, TypeError):
                pass
    if prices:
        purchase_price = min(prices)

    # Total cost of ownership (5 years)
    five_year_energy = round(cost["yearly"] * 5, 2)
    five_year_total = round(purchase_price + five_year_energy, 2)

    # CO2 emissions
    co2_yearly = round(consumption["yearly_kwh"] * CO2_PER_KWH, 2)

    result = {
        "product_id": product_id,
        "product_name": name,
        "category": category,
        "wattage": wattage,
        "usage_hours_per_day": usage_hours,
        "efficiency_rating": efficiency_rating,
        "efficiency_factor": round(efficiency_factor, 2),
        "consumption": consumption,
        "cost_tnd": cost,
        "total_cost_of_ownership": {
            "purchase_price": purchase_price,
            "five_year_energy_cost": five_year_energy,
            "five_year_total": five_year_total,
        },
        "co2_emissions_kg_per_year": co2_yearly,
        "calculated_at": datetime.utcnow().isoformat(),
    }

    # Store for ML learning (fire and forget)
    try:
        energy_db = db.client["energy"]
        await energy_db["calculations"].insert_one({
            **result,
            "stored_at": datetime.utcnow(),
        })
    except Exception:
        pass  # Non-critical

    return result


async def compare_products(product_ids: List[str]) -> Optional[Dict[str, Any]]:
    """Compare energy consumption of multiple products"""
    results = []

    for pid in product_ids:
        calc = await calculate_product_energy(pid)
        if calc:
            results.append(calc)

    if not results:
        return None

    # Sort by yearly cost (cheapest first)
    results.sort(key=lambda x: x["cost_tnd"]["yearly"])

    worst_yearly = results[-1]["cost_tnd"]["yearly"] if results else 0

    comparison = []
    for i, r in enumerate(results):
        savings = round(worst_yearly - r["cost_tnd"]["yearly"], 2)
        item = {
            "product_id": r["product_id"],
            "product_name": r["product_name"],
            "category": r["category"],
            "wattage": r["wattage"],
            "efficiency_rating": r["efficiency_rating"],
            "efficiency_rank": i + 1,
            "yearly_savings_vs_worst": savings,
            "consumption": r["consumption"],
            "cost_tnd": r["cost_tnd"],
            "total_cost_of_ownership": r["total_cost_of_ownership"],
            "co2_emissions_kg_per_year": r["co2_emissions_kg_per_year"],
        }
        comparison.append(item)

    return {
        "comparison": comparison,
        "most_efficient": comparison[0] if comparison else None,
        "least_efficient": comparison[-1] if comparison else None,
        "total_devices": len(comparison),
    }


def get_tips(category: str) -> Dict[str, Any]:
    """Get energy saving tips for a device category"""
    cat = category.lower().strip()

    if cat in ENERGY_SAVING_TIPS:
        return {"category": cat, "tips": ENERGY_SAVING_TIPS[cat]}

    # Default tips
    return {
        "category": cat,
        "tips": [
            "Éteignez l'appareil quand il n'est pas utilisé",
            "Utilisez le mode économie d'énergie si disponible",
            "Débranchez l'appareil pour éviter la consommation en veille",
            "Entretenez l'appareil régulièrement pour une efficacité optimale",
            "Envisagez un modèle plus économe lors du remplacement",
        ],
    }


def get_all_categories() -> Dict[str, Dict[str, Any]]:
    """Get all supported device categories with their configurations"""
    categories = {}
    for key, config in DEVICE_CATEGORIES.items():
        categories[key] = {
            "typical_wattage": config["typical_wattage"],
            "usage_hours_per_day": config["usage_hours_per_day"],
            "efficiency_factor": config["efficiency_factor"],
            "standby_ratio": config["standby_ratio"],
        }
    return categories
