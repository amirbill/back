from datetime import datetime, timezone
import re
from typing import Any, List, Literal, Optional

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


BlogSectionType = Literal["h2", "h3", "p", "ul", "highlight"]


class BlogSectionPayload(BaseModel):
    type: BlogSectionType
    text: Optional[str] = None
    items: List[str] = Field(default_factory=list)


class BlogPayload(BaseModel):
    slug: Optional[str] = None
    category: str = Field(min_length=1)
    categoryColor: str = Field(min_length=1)
    title: str = Field(min_length=1)
    desc: str = Field(min_length=1)
    img: str = Field(min_length=1)
    read: str = Field(min_length=1)
    date: str = Field(min_length=1)
    sections: List[BlogSectionPayload] = Field(default_factory=list)


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


def _blogs_collection():
    return get_auth_database()["blogs"]


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


def _serialize_blog(document: dict[str, Any]) -> dict[str, Any]:
    document = dict(document)
    document["_id"] = str(document.get("_id"))
    for key in ("created_at", "updated_at"):
        value = document.get(key)
        if isinstance(value, datetime):
            document[key] = value.isoformat()
        elif value is None:
            document[key] = None
        else:
            document[key] = str(value)
    return document


def _normalize_rule_path(path: str) -> str:
    cleaned = path.strip()
    if not cleaned:
        return "/"
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    if len(cleaned) > 1:
        cleaned = cleaned.rstrip("/")
    return cleaned


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "blog"


async def _build_unique_blog_slug(base_slug: str) -> str:
    slug = _slugify(base_slug)
    candidate = slug
    index = 2
    while await _blogs_collection().find_one({"slug": candidate}):
        candidate = f"{slug}-{index}"
        index += 1
    return candidate


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


async def _delete_user_documents(user_id: str):
    collection, document = await _find_user_document(user_id)
    if collection is None or document is None:
        raise HTTPException(status_code=404, detail="User not found")

    email = str(document.get("email", "")).strip().lower()
    target_ids: list[Any] = [document.get("_id"), user_id]
    try:
        target_ids.append(ObjectId(user_id))
    except Exception:
        pass

    matched_ids_by_collection: dict[Any, list[Any]] = {
        _users_collection(): [],
        _secondary_users_collection(): [],
    }

    for current_collection in matched_ids_by_collection:
        filters: list[dict[str, Any]] = []
        for target_id in target_ids:
            if target_id is None:
                continue
            filters.append({"_id": target_id})

        if email:
            filters.append({"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}})

        if not filters:
            continue

        cursor = current_collection.find({"$or": filters}, {"_id": 1})
        matches = await cursor.to_list(length=None)
        matched_ids_by_collection[current_collection] = [match["_id"] for match in matches if match.get("_id") is not None]

    deleted_count = 0
    for current_collection, matched_ids in matched_ids_by_collection.items():
        if not matched_ids:
            continue
        result = await current_collection.delete_many({"_id": {"$in": matched_ids}})
        deleted_count += result.deleted_count

    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": "User deleted"}


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


async def _update_user_role_impl(
    user_id: str,
    payload: UpdateUserRolePayload,
    _: UserResponse,
):
    collection, document = await _find_user_document(user_id)
    if collection is None or document is None:
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


@router.post("/users/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: str,
    payload: UpdateUserRolePayload,
    current_user: UserResponse = Depends(require_superadmin),
):
    return await _update_user_role_impl(user_id, payload, current_user)


@router.patch("/users/{user_id}/role", response_model=UserResponse)
async def update_user_role_patch(
    user_id: str,
    payload: UpdateUserRolePayload,
    current_user: UserResponse = Depends(require_superadmin),
):
    return await _update_user_role_impl(user_id, payload, current_user)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: UserResponse = Depends(require_superadmin),
):
    current_user_id = str(current_user.id or "")
    if current_user_id and current_user_id == user_id:
        raise HTTPException(status_code=403, detail="You cannot delete your own account")

    return await _delete_user_documents(user_id)


@router.get("/access-rules")
async def list_access_rules(_: UserResponse = Depends(require_superadmin)):
    cursor = _rules_collection().find({}).sort("category", 1).sort("label", 1)
    rules = await cursor.to_list(length=None)
    return [_serialize_rule(rule) for rule in rules]


@router.get("/access-rules/public")
async def list_public_access_rules():
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
        "path": _normalize_rule_path(payload.path),
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


@router.get("/blogs")
async def list_admin_blogs(_: UserResponse = Depends(require_superadmin)):
    cursor = _blogs_collection().find({}).sort("updated_at", -1)
    blogs = await cursor.to_list(length=None)
    return [_serialize_blog(blog) for blog in blogs]


@router.post("/blogs")
async def create_blog(payload: BlogPayload, _: UserResponse = Depends(require_superadmin)):
    now = datetime.now(timezone.utc)
    slug = await _build_unique_blog_slug(payload.slug or payload.title)
    blog_document = {
        "slug": slug,
        "category": payload.category.strip(),
        "categoryColor": payload.categoryColor.strip(),
        "title": payload.title.strip(),
        "desc": payload.desc.strip(),
        "img": payload.img.strip(),
        "read": payload.read.strip(),
        "date": payload.date.strip(),
        "sections": [
            {
                "type": section.type,
                "text": section.text.strip() if section.text else None,
                "items": [item.strip() for item in section.items if item.strip()],
            }
            for section in payload.sections
        ],
        "created_at": now,
        "updated_at": now,
    }

    result = await _blogs_collection().insert_one(blog_document)
    saved_blog = await _blogs_collection().find_one({"_id": result.inserted_id})
    if not saved_blog:
        raise HTTPException(status_code=500, detail="Unable to save blog")
    return _serialize_blog(saved_blog)


@router.delete("/blogs/{blog_id}")
async def delete_blog(blog_id: str, _: UserResponse = Depends(require_superadmin)):
    target_ids: list[Any] = [blog_id]
    try:
        target_ids.insert(0, ObjectId(blog_id))
    except Exception:
        pass

    result = await _blogs_collection().delete_one({"_id": {"$in": target_ids}})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Blog not found")
    return {"message": "Blog deleted"}
