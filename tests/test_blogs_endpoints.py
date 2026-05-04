from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _auth_header(email: str = "superadmin@example.com"):
    from app.core.security import create_access_token

    token = create_access_token(subject=email)
    return {"Authorization": f"Bearer {token}"}


def _blog_doc():
    return {
        "_id": "blog-1",
        "slug": "new-blog",
        "category": "Guides",
        "categoryColor": "#3BDEB9",
        "title": "New Blog",
        "desc": "Description",
        "img": "data:image/png;base64,abc",
        "read": "5 min",
        "date": "May 2026",
        "sections": [{"type": "p", "text": "Paragraph", "items": []}],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


def test_public_blogs_endpoint_returns_saved_blogs(client):
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[_blog_doc()])
    mock_collection = MagicMock()
    mock_collection.find.return_value.sort.return_value = mock_cursor

    with patch("app.api.endpoints.blogs._blogs_collection", return_value=mock_collection):
        response = client.get("/api/v1/blogs")

    assert response.status_code == 200
    assert response.json()[0]["slug"] == "new-blog"


def test_admin_create_blog_returns_saved_blog(client):
    from app.main import app
    from app.db.mongodb import get_auth_database

    superadmin_doc = {
        "_id": "superadmin-id",
        "email": "superadmin@example.com",
        "password_hash": "hashed",
        "role": "superadmin",
        "is_verified": True,
        "is_active": True,
    }
    auth_db = MagicMock()
    auth_db.users.find_one = AsyncMock(return_value=superadmin_doc)
    app.dependency_overrides[get_auth_database] = lambda: auth_db

    inserted = MagicMock(inserted_id="inserted-blog")
    saved_blog = {**_blog_doc(), "_id": "inserted-blog"}
    blog_collection = MagicMock()
    blog_collection.find_one = AsyncMock(side_effect=[None, saved_blog])
    blog_collection.insert_one = AsyncMock(return_value=inserted)

    try:
        with patch("app.api.endpoints.admin._blogs_collection", return_value=blog_collection):
            response = client.post(
                "/api/v1/admin/blogs",
                headers=_auth_header(),
                json={
                    "category": "Guides",
                    "categoryColor": "#3BDEB9",
                    "title": "New Blog",
                    "desc": "Description",
                    "img": "data:image/png;base64,abc",
                    "read": "5 min",
                    "date": "May 2026",
                    "sections": [{"type": "p", "text": "Paragraph", "items": []}],
                },
            )
    finally:
        app.dependency_overrides.pop(get_auth_database, None)

    assert response.status_code == 200
    assert response.json()["slug"] == "new-blog"
