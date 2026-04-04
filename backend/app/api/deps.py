from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.schemas.auth import CurrentUser

security = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for dependency injection."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> CurrentUser:
    """Validate Bearer token (JWT from NextAuth) and extract user info.

    Decodes the JWT using the AUTH_SECRET and returns a CurrentUser object.
    For now this performs basic JWT validation; full user lookup from DB
    will be added once the auth flow is wired end-to-end.
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.AUTH_SECRET,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
        sub: str | None = payload.get("sub")
        email: str | None = payload.get("email")
        if sub is None or email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    return CurrentUser(
        id=payload.get("sub"),
        org_id=payload.get("org_id", "00000000-0000-0000-0000-000000000000"),
        email=payload.get("email", ""),
        name=payload.get("name", ""),
        role=payload.get("role", "member"),
    )
