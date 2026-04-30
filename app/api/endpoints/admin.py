from datetime import datetime, timezone
from typing import Any, List, Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.endpoints.auth import get_current_user
from app.db.mongodb import get_auth_database, get_database
from app.schemas.auth import UserResponse

router = APIRouter()

RoleName = Literal["client", "admin", "superadmin"]


class UpdateUserRolePayload(BaseModel):
    role: RoleName


class AccessRulePayload(BaseModel):
    path: str = Field(min_length=1)
    label: str = Field(min_length=1)
    category: str = Field(default="Custom")
    visible: bool = True
    allowed_roles: List[RoleName] = Field(default_factory=list)
    allowed_emails: List[str] = Field(default_factory=list)


def require_superadmin(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    if current_user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return current_user


def _users_collection():
    return get_auth_database()["users"]


def _secondary_users_collection():
    return get_database()["users"]


def _rules_collection():
    return get_auth_database()["page_access_rules"]


def _serialize_user(document: dict[str, Any]) -> dict[str, Any]:
    document = dict(document)
    document["_id"] = str(document.get("_id"))
    return document


def _serialize_rule(document: dict[str, Any]) -> dict[str, Any]:
    document = dict(document)
    document["_id"] = str(document.get("_id"))
    updated_at = document.get("updated_at")
    if isinstance(updated_at, datetime):
        document["updated_at"] = updated_at.isoformat()
    elif updated_at is None:
        document["updated_at"] = None
    else:
        document["updated_at"] = str(updated_at)
    return document


async def _find_user_document(user_id: str):
    collections = [_users_collection(), _secondary_users_collection()]

    object_id = None
    try:
        object_id = ObjectId(user_id)
    except Exception:
        object_id = None

    for collection in collections:
        document = await collection.find_one({"_id": object_id}) if object_id is not None else None
        if document:
            return collection, document

        document = await collection.find_one({"_id": user_id})
        if document:
            return collection, document

    return None, None


@router.get("/users", response_model=List[UserResponse])
async def list_users(_: UserResponse = Depends(require_superadmin)):
    users_by_email: dict[str, dict[str, Any]] = {}

    for collection in (_users_collection(), _secondary_users_collection()):
        cursor = collection.find({}).sort("email", 1)
        for user in await cursor.to_list(length=None):
            email = str(user.get("email", "")).strip().lower()
            if not email:
                continue
            users_by_email[email] = user

    users = sorted(users_by_email.values(), key=lambda item: str(item.get("email", "")).lower())
    return [_serialize_user(user) for user in users]


@router.patch("/users/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: str,
    payload: UpdateUserRolePayload,
    _: UserResponse = Depends(require_superadmin),
):
    collection, document = await _find_user_document(user_id)
    if not collection or not document:
        raise HTTPException(status_code=404, detail="User not found")

    result = await collection.update_one(
        {"_id": document["_id"]},
        {"$set": {"role": payload.role, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    updated_user = await collection.find_one({"_id": document["_id"]})
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    return _serialize_user(updated_user)


@router.get("/access-rules")
async def list_access_rules(_: UserResponse = Depends(require_superadmin)):
    cursor = _rules_collection().find({}).sort("category", 1).sort("label", 1)
    rules = await cursor.to_list(length=None)
    return [_serialize_rule(rule) for rule in rules]


@router.post("/access-rules")
async def upsert_access_rule(
    payload: AccessRulePayload,
    _: UserResponse = Depends(require_superadmin),
):
    now = datetime.now(timezone.utc)
    rule_document = {
        "path": payload.path.strip(),
        "label": payload.label.strip(),
        "category": payload.category.strip() or "Custom",
        "visible": payload.visible,
        "allowed_roles": payload.allowed_roles,
        "allowed_emails": [email.strip().lower() for email in payload.allowed_emails if email.strip()],
        "updated_at": now,
    }

    await _rules_collection().update_one(
        {"path": rule_document["path"]},
        {"$set": rule_document, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    saved_rule = await _rules_collection().find_one({"path": rule_document["path"]})
    if not saved_rule:
        raise HTTPException(status_code=500, detail="Unable to save access rule")

    return _serialize_rule(saved_rule)


@router.delete("/access-rules")
async def delete_access_rule(path: str, _: UserResponse = Depends(require_superadmin)):
    result = await _rules_collection().delete_one({"path": path})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Access rule not found")
    return {"message": "Access rule deleted"}