from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.endpoints.auth import get_current_user
from app.db.mongodb import get_auth_database
from app.schemas.auth import UserResponse

router = APIRouter()

AudienceRole = Literal["client", "admin"]


class NotificationPayload(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    product_id: Optional[str] = None
    product_name: str = Field(min_length=1, max_length=240)
    product_url: str = Field(min_length=1, max_length=1000)
    audience_roles: List[AudienceRole] = Field(default_factory=lambda: ["client", "admin"])


class NotificationResponse(BaseModel):
    id: str = Field(alias="_id", serialization_alias="_id")
    text: str
    product_id: Optional[str] = None
    product_name: str
    product_url: str
    audience_roles: List[AudienceRole]
    created_by_email: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_read: bool = False

    model_config = {"populate_by_name": True}


def require_superadmin(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    if current_user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return current_user


def _notifications_collection():
    return get_auth_database()["notifications"]


def _serialize_datetime(value: Any):
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _serialize_notification(document: dict[str, Any], current_email: Optional[str] = None):
    item = dict(document)
    item["_id"] = str(item.get("_id"))
    item["created_at"] = _serialize_datetime(item.get("created_at"))
    item["updated_at"] = _serialize_datetime(item.get("updated_at"))
    read_by = [str(email).strip().lower() for email in item.get("read_by", []) if str(email).strip()]
    item["is_read"] = bool(current_email and current_email.strip().lower() in read_by)
    item.pop("read_by", None)
    item.pop("dismissed_by", None)
    return item


@router.get("/me", response_model=List[NotificationResponse])
async def list_my_notifications(current_user: UserResponse = Depends(get_current_user)):
    user_role = (current_user.role or "client").strip().lower()
    if user_role not in {"client", "admin"}:
        return []

    email = current_user.email.strip().lower()
    cursor = _notifications_collection().find(
        {
            "audience_roles": user_role,
            "dismissed_by": {"$ne": email},
        }
    ).sort("created_at", -1)
    notifications = await cursor.to_list(length=50)
    return [_serialize_notification(item, current_user.email) for item in notifications]


@router.post("/broadcast", response_model=NotificationResponse)
async def create_notification(
    payload: NotificationPayload,
    current_user: UserResponse = Depends(require_superadmin),
):
    now = datetime.now(timezone.utc)
    audience_roles = list(dict.fromkeys(payload.audience_roles or ["client", "admin"]))
    notification_document = {
        "text": payload.text.strip(),
        "product_id": payload.product_id.strip() if payload.product_id else None,
        "product_name": payload.product_name.strip(),
        "product_url": payload.product_url.strip(),
        "audience_roles": audience_roles,
        "created_by_email": current_user.email,
        "created_at": now,
        "updated_at": now,
        "read_by": [],
    }

    result = await _notifications_collection().insert_one(notification_document)
    saved = await _notifications_collection().find_one({"_id": result.inserted_id})
    if not saved:
        raise HTTPException(status_code=500, detail="Unable to save notification")
    return _serialize_notification(saved, current_user.email)


@router.get("/broadcasts", response_model=List[NotificationResponse])
async def list_broadcast_notifications(_: UserResponse = Depends(require_superadmin)):
    cursor = _notifications_collection().find({}).sort("created_at", -1)
    notifications = await cursor.to_list(length=100)
    return [_serialize_notification(item) for item in notifications]


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_as_read(
    notification_id: str,
    current_user: UserResponse = Depends(get_current_user),
):
    target_id: Any = notification_id
    try:
        target_id = ObjectId(notification_id)
    except Exception:
        target_id = notification_id

    email = current_user.email.strip().lower()
    await _notifications_collection().update_one(
        {"_id": target_id},
        {
            "$addToSet": {"read_by": email},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )

    saved = await _notifications_collection().find_one({"_id": target_id})
    if not saved:
        raise HTTPException(status_code=404, detail="Notification not found")
    return _serialize_notification(saved, current_user.email)


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user: UserResponse = Depends(get_current_user),
):
    target_id: Any = notification_id
    try:
        target_id = ObjectId(notification_id)
    except Exception:
        target_id = notification_id

    if current_user.role == "superadmin":
        result = await _notifications_collection().delete_one({"_id": target_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Notification not found")
        return {"message": "Notification deleted"}

    user_role = (current_user.role or "client").strip().lower()
    if user_role not in {"client", "admin"}:
        raise HTTPException(status_code=403, detail="Notification delete not allowed for this role")

    email = current_user.email.strip().lower()
    result = await _notifications_collection().update_one(
        {
            "_id": target_id,
            "audience_roles": user_role,
        },
        {
            "$addToSet": {"dismissed_by": email},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"message": "Notification dismissed"}
