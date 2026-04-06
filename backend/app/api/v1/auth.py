from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.user import Organization, User

router = APIRouter()


class EnsureUserRequest(BaseModel):
    email: str
    name: str
    picture: str | None = None


class EnsureUserResponse(BaseModel):
    user_id: str
    org_id: str
    role: str


@router.post("/ensure-user", response_model=EnsureUserResponse)
async def ensure_user(
    body: EnsureUserRequest,
    db: AsyncSession = Depends(get_db),
) -> EnsureUserResponse:
    """Find or create the user and their organization.

    Called by the Next.js proxy before issuing a JWT so the token
    contains a real org_id that satisfies foreign-key constraints.
    """
    # Look up existing user by email
    stmt = select(User).where(User.email == body.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        return EnsureUserResponse(
            user_id=str(user.id),
            org_id=str(user.org_id),
            role=user.role,
        )

    # No user yet — create org + user
    domain = body.email.split("@")[-1]

    # Check if an org for this domain already exists
    org_stmt = select(Organization).where(Organization.name == domain)
    org_result = await db.execute(org_stmt)
    org = org_result.scalar_one_or_none()

    if not org:
        org = Organization(name=domain)
        db.add(org)
        await db.flush()

    user = User(
        org_id=org.id,
        email=body.email,
        name=body.name,
        picture=body.picture,
        role="admin",  # First user in org gets admin
    )
    db.add(user)
    await db.flush()

    return EnsureUserResponse(
        user_id=str(user.id),
        org_id=str(org.id),
        role=user.role,
    )
