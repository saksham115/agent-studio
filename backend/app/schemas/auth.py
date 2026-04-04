import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class TokenPayload(BaseModel):
    """JWT token payload extracted from NextAuth."""
    sub: str
    email: str
    name: str | None = None
    picture: str | None = None
    exp: int | None = None


class CurrentUser(BaseModel):
    """Represents the currently authenticated user."""
    id: uuid.UUID
    org_id: uuid.UUID
    email: str
    name: str
    role: str = "member"


class UserResponse(BaseModel):
    """User information returned in API responses."""
    id: uuid.UUID
    org_id: uuid.UUID
    email: str
    name: str
    picture: str | None = None
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
