from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.endpoints.admin import _blogs_collection, _serialize_blog

router = APIRouter()


@router.get("")
async def list_public_blogs():
    cursor = _blogs_collection().find({}).sort("updated_at", -1)
    blogs = await cursor.to_list(length=None)
    return [_serialize_blog(blog) for blog in blogs]


@router.get("/{slug}")
async def get_public_blog(slug: str):
    blog = await _blogs_collection().find_one({"slug": slug.strip().lower()})
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    return _serialize_blog(blog)
