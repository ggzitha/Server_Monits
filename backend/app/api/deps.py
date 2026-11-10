from datetime import datetime, timezone
from typing import Optional, Set
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.core.csrf import validate_csrf_token
from backend.app.core.rbac import user_has_permission
from backend.app.core.security import decode_access_token, hash_token
from backend.app.db.models.auth_tokens import ApiToken, UserSession
from backend.app.db.models.system_config import SystemConfig
from backend.app.db.models.user import User
from backend.app.db.session import get_db


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime object is timezone-aware UTC across all database engines."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def is_system_initialized(db: AsyncSession) -> bool:
    """Check if the system has completed initial setup."""
    try:
        stmt = select(SystemConfig).where(SystemConfig.key == "is_initialized")
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()
        if config and config.value.lower() in ("true", "1", "yes"):
            return True
        
        # Check if any admin user exists
        user_stmt = select(User).limit(1)
        user_res = await db.execute(user_stmt)
        return user_res.scalar_one_or_none() is not None
    except Exception:
        return False


async def require_uninitialized(db: AsyncSession = Depends(get_db)) -> None:
    """Ensure setup endpoints are only accessible prior to initial setup. Returns 403 post-init."""
    if await is_system_initialized(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System is already initialized. Setup endpoints are locked."
        )


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_token: Optional[str] = Cookie(None, alias=settings.SESSION_COOKIE_NAME),
    authorization: Optional[str] = Header(None),
) -> Optional[User]:
    """Retrieve current user from session cookie, JWT bearer, or scoped API token."""
    now = datetime.now(timezone.utc)
    
    # 1. Check Bearer Authorization Header
    if authorization and authorization.startswith("Bearer "):
        token_str = authorization[7:].strip()
        
        # Try JWT decode
        jwt_payload = decode_access_token(token_str)
        if jwt_payload and "sub" in jwt_payload:
            user_id = jwt_payload["sub"]
            stmt = select(User).options(selectinload(User.roles)).where(User.id == user_id)
            res = await db.execute(stmt)
            user = res.scalar_one_or_none()
            if user and user.is_active:
                return user

        # Try API Token (hashed lookup)
        token_hashed = hash_token(token_str)
        api_token_stmt = select(ApiToken).options(selectinload(ApiToken.user).selectinload(User.roles)).where(
            ApiToken.token_hash == token_hashed
        )
        api_res = await db.execute(api_token_stmt)
        api_token = api_res.scalar_one_or_none()
        if api_token:
            if api_token.expires_at and ensure_utc(api_token.expires_at) < now:
                return None
            api_token.last_used_at = now
            await db.commit()
            if api_token.user and api_token.user.is_active:
                return api_token.user

    # 2. Check Session Cookie
    if session_token:
        sess_stmt = select(UserSession).options(selectinload(UserSession.user).selectinload(User.roles)).where(
            UserSession.session_token == session_token
        )
        sess_res = await db.execute(sess_stmt)
        session_obj = sess_res.scalar_one_or_none()
        if session_obj:
            if ensure_utc(session_obj.expires_at) < now:
                await db.delete(session_obj)
                await db.commit()
                return None
            if session_obj.user and session_obj.user.is_active:
                return session_obj.user

    return None


async def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional),
) -> User:
    """Enforce authenticated user requirement."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check account lock
    if user.locked_until:
        if ensure_utc(user.locked_until) > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is temporarily locked due to repeated failed logins",
            )

    return user


def require_permission(required_permission: str):
    """Dependency factory checking if current user has the specified permission."""
    async def permission_checker(current_user: User = Depends(get_current_user)) -> User:
        user_permissions: Set[str] = set()
        for role in current_user.roles:
            for perm in role.permissions:
                user_permissions.add(perm)
        
        if not user_has_permission(user_permissions, required_permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: Missing '{required_permission}' permission",
            )
        return current_user
    return permission_checker


async def verify_metrics_access(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> None:
    """Ensure /metrics is strictly accessible only by authenticated Admin users.
    
    Source IP addresses and X-Forwarded-For headers are never trusted.
    """
    if current_user:
        for role in current_user.roles:
            if role.name == "Admin" or "*" in role.permissions:
                return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Metrics endpoint is restricted to administrators",
    )
