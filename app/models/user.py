from typing import Optional, Annotated, Any
from pydantic import BaseModel, EmailStr, Field, BeforeValidator
from datetime import datetime
from bson import ObjectId

def validate_object_id(v: Any) -> str:
    if isinstance(v, ObjectId):
        return str(v)
    return str(v)

PyObjectId = Annotated[str, BeforeValidator(validate_object_id)]

class User(BaseModel):
    id: Optional[PyObjectId] = Field(None, alias="_id")
    email: EmailStr
    password_hash: str
    role: str = "client" # client | admin | superadmin
    full_name: Optional[str] = None
    username: Optional[str] = None
    birthdate: Optional[str] = None
    address: Optional[str] = None
    is_active: bool = True
    is_verified: bool = False
    verification_code: Optional[str] = None
    reset_token: Optional[str] = None
    reset_code: Optional[str] = None
    reset_code_expires: Optional[datetime] = None
    google_id: Optional[str] = None
    picture: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True
    }
