import csv
import io
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.endpoints.auth import get_current_user
from app.db.mongodb import get_auth_database
from app.schemas.auth import UserResponse

router = APIRouter()

ImportSource = Literal["retail", "para"]
ImportSectionKey = Literal["home_trending", "appliance_showcase"]

IMPORT_SECTIONS: dict[str, dict[str, str]] = {
    "home_trending": {
        "label": "Trending home",
        "source": "retail",
        "category_type": "top_category",
    },
    "appliance_showcase": {
        "label": "Appliance showcase",
        "source": "retail",
        "category_type": "top_category",
    },
}

CATEGORY_ALIASES: dict[str, list[str]] = {
    "Réfrigérateur": ["Réfrigérateur", "RÃ©frigÃ©rateur"],
    "RÃ©frigÃ©rateur": ["Réfrigérateur", "RÃ©frigÃ©rateur"],
    "Machine à Laver": ["Machine à Laver", "Machine Ã  Laver"],
    "Machine Ã  Laver": ["Machine à Laver", "Machine Ã  Laver"],
}


class ImportedShopPrice(BaseModel):
    shop: str
    price: float
    oldPrice: Optional[float] = None
    available: bool = False
    url: Optional[str] = None


class ImportedProduct(BaseModel):
    id: str
    name: str
    brand: str
    bestPrice: float
    originalPrice: Optional[float] = None
    image: str
    description: str
    inStock: bool
    category: Optional[str] = None
    href: Optional[str] = None
    shopPrices: list[ImportedShopPrice] = Field(default_factory=list)
    specifications: Optional[dict[str, Any]] = None


class ImportedContentRecord(BaseModel):
    _id: str
    section_key: str
    section_label: str
    source: str
    category: str
    category_type: str
    file_name: str
    imported_count: int
    replace_existing: bool
    imported_by_email: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    products: list[ImportedProduct] = Field(default_factory=list)


class SectionDefinition(BaseModel):
    key: str
    label: str
    source: str
    category_type: str


def require_superadmin(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    if current_user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return current_user


def _imports_collection():
    return get_auth_database()["content_imports"]


def _category_candidates(category: str):
    cleaned = category.strip()
    aliases = CATEGORY_ALIASES.get(cleaned, [cleaned])
    return list(dict.fromkeys([item.strip() for item in aliases if item and item.strip()]))


def _serialize_datetime(value: Any):
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _serialize_import(document: dict[str, Any]) -> dict[str, Any]:
    item = dict(document)
    item["_id"] = str(item.get("_id"))
    item["created_at"] = _serialize_datetime(item.get("created_at"))
    item["updated_at"] = _serialize_datetime(item.get("updated_at"))
    return item


def _parse_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    text = str(value).strip().replace(",", ".")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "oui", "y"}:
        return True
    if text in {"0", "false", "no", "non", "n"}:
        return False
    return default


def _parse_shop_prices(row: dict[str, Any], product_url: Optional[str]) -> list[dict[str, Any]]:
    prices: list[dict[str, Any]] = []
    for index in range(1, 6):
        prefix = f"shop{index}"
        shop_name = str(row.get(f"{prefix}_name", "")).strip()
        shop_price = _parse_float(row.get(f"{prefix}_price"))
        if not shop_name or shop_price is None:
            continue
        prices.append(
            {
                "shop": shop_name,
                "price": shop_price,
                "oldPrice": _parse_float(row.get(f"{prefix}_old_price")),
                "available": _parse_bool(row.get(f"{prefix}_available"), True),
                "url": str(row.get(f"{prefix}_url", "")).strip() or product_url or None,
            }
        )
    return prices


def _build_imported_products(csv_text: str, category: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file is empty or missing headers")

    normalized_headers = {header.strip().lower() for header in reader.fieldnames if header}
    if "name" not in normalized_headers:
        raise HTTPException(status_code=400, detail="CSV must include at least a 'name' column")

    products: list[dict[str, Any]] = []
    for row_index, raw_row in enumerate(reader, start=1):
        row = {str(key).strip().lower(): value for key, value in raw_row.items() if key is not None}
        name = str(row.get("name", "")).strip()
        if not name:
            continue

        product_url = str(row.get("product_url", "")).strip() or None
        shop_prices = _parse_shop_prices(row, product_url)
        best_price = _parse_float(row.get("best_price"))
        if best_price is None and shop_prices:
            best_price = min(price["price"] for price in shop_prices)
        if best_price is None:
            raise HTTPException(status_code=400, detail=f"Row {row_index} is missing a valid best_price")

        product_id = str(ObjectId())
        products.append(
            {
                "id": product_id,
                "name": name,
                "brand": str(row.get("brand", "")).strip() or "Produit",
                "bestPrice": best_price,
                "originalPrice": _parse_float(row.get("original_price")),
                "image": str(row.get("image", "")).strip() or "/images/item-cart.png",
                "description": str(row.get("description", "")).strip() or name,
                "inStock": _parse_bool(row.get("in_stock"), True),
                "category": str(row.get("category", "")).strip() or category,
                "href": product_url,
                "shopPrices": shop_prices,
                "specifications": None,
            }
        )

    if not products:
        raise HTTPException(status_code=400, detail="CSV does not contain any valid product rows")

    return products


@router.get("/sections", response_model=list[SectionDefinition])
async def list_import_sections():
    return [
        {
            "key": key,
            "label": value["label"],
            "source": value["source"],
            "category_type": value["category_type"],
        }
        for key, value in IMPORT_SECTIONS.items()
    ]


@router.get("/section-data", response_model=Optional[ImportedContentRecord])
async def get_imported_section_data(section_key: str, category: str):
    document = await _imports_collection().find_one(
        {"section_key": section_key, "category": {"$in": _category_candidates(category)}},
        sort=[("created_at", -1)],
    )
    if not document:
        return None
    return _serialize_import(document)


@router.get("/history", response_model=list[ImportedContentRecord])
async def list_import_history(_: UserResponse = Depends(require_superadmin)):
    cursor = _imports_collection().find({}).sort("created_at", -1)
    items = await cursor.to_list(length=100)
    return [_serialize_import(item) for item in items]


@router.delete("/{import_id}")
async def delete_import_record(import_id: str, _: UserResponse = Depends(require_superadmin)):
    target_ids: list[Any] = [import_id]
    try:
        target_ids.insert(0, ObjectId(import_id))
    except Exception:
        pass

    result = await _imports_collection().delete_one({"_id": {"$in": target_ids}})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Imported file not found")
    return {"message": "Imported file deleted"}


@router.post("/upload", response_model=ImportedContentRecord)
async def upload_import_file(
    section_key: ImportSectionKey = Form(...),
    category: str = Form(...),
    replace_existing: bool = Form(True),
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(require_superadmin),
):
    section_meta = IMPORT_SECTIONS.get(section_key)
    if not section_meta:
        raise HTTPException(status_code=400, detail="Unknown import section")

    file_name = file.filename or "import.csv"
    if not file_name.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    content = await file.read()
    try:
        csv_text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded")

    products = _build_imported_products(csv_text, category.strip())
    now = datetime.now(timezone.utc)

    if replace_existing:
        await _imports_collection().delete_many({"section_key": section_key, "category": category.strip()})

    document = {
        "section_key": section_key,
        "section_label": section_meta["label"],
        "source": section_meta["source"],
        "category": category.strip(),
        "category_type": section_meta["category_type"],
        "file_name": file_name,
        "imported_count": len(products),
        "replace_existing": replace_existing,
        "imported_by_email": current_user.email,
        "created_at": now,
        "updated_at": now,
        "products": products,
    }

    result = await _imports_collection().insert_one(document)
    saved = await _imports_collection().find_one({"_id": result.inserted_id})
    if not saved:
        raise HTTPException(status_code=500, detail="Unable to save imported content")
    return _serialize_import(saved)
