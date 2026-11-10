from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.deps import get_db, require_permission
from backend.app.core.audit import record_audit_log
from backend.app.core.security import hash_password
from backend.app.db.models.user import Role, User

router = APIRouter(prefix="/users", tags=["users"])


class UserCreateRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    role_names: List[str] = ["Viewer"]
    preferred_lang: str = "en"
    preferred_theme: str = "neon"


class UserUpdateRequest(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    role_names: Optional[List[str]] = None
    preferred_lang: Optional[str] = None
    preferred_theme: Optional[str] = None


@router.get("", dependencies=[Depends(require_permission("users:read"))])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List users with pagination and search filter."""
    stmt = select(User).options(selectinload(User.roles)).order_by(User.created_at.desc())
    if search:
        search_filter = f"%{search}%"
        stmt = stmt.where((User.username.ilike(search_filter)) | (User.email.ilike(search_filter)))
    
    total_stmt = select(func.count(User.id))
    if search:
        total_stmt = total_stmt.where((User.username.ilike(search_filter)) | (User.email.ilike(search_filter)))

    total_res = await db.execute(total_stmt)
    total = total_res.scalar_one()

    res = await db.execute(stmt.offset(skip).limit(limit))
    users = res.scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "is_active": u.is_active,
                "is_totp_enabled": u.is_totp_enabled,
                "roles": [r.name for r in u.roles],
                "last_login_at": u.last_login_at,
                "created_at": u.created_at,
            }
            for u in users
        ],
    }


@router.post("", dependencies=[Depends(require_permission("users:write"))])
async def create_user(
    req: UserCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a new user with assigned roles."""
    # Check duplicate
    stmt = select(User).where((User.username == req.username) | (User.email == req.email))
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username or email already in use")

    # Fetch roles
    roles_stmt = select(Role).where(Role.name.in_(req.role_names))
    roles_res = await db.execute(roles_stmt)
    assigned_roles = roles_res.scalars().all()

    new_user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
        is_active=True,
        preferred_lang=req.preferred_lang,
        preferred_theme=req.preferred_theme,
    )
    new_user.roles = list(assigned_roles)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    await record_audit_log(
        db, "USER_CREATE", resource_type="users", resource_id=new_user.id,
        details={"username": new_user.username, "roles": req.role_names}, request=request
    )

    return {
        "id": new_user.id,
        "username": new_user.username,
        "email": new_user.email,
        "roles": [r.name for r in new_user.roles],
    }


@router.get("/{user_id}", dependencies=[Depends(require_permission("users:read"))])
async def get_user(user_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch single user by ID."""
    stmt = select(User).options(selectinload(User.roles)).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
        "is_totp_enabled": user.is_totp_enabled,
        "preferred_lang": user.preferred_lang,
        "preferred_theme": user.preferred_theme,
        "roles": [r.name for r in user.roles],
        "created_at": user.created_at,
    }


@router.put("/{user_id}", dependencies=[Depends(require_permission("users:write"))])
async def update_user(
    user_id: str,
    req: UserUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Update user attributes, status, password or roles."""
    stmt = select(User).options(selectinload(User.roles)).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if req.email and req.email != user.email:
        chk = await db.execute(select(User).where(User.email == req.email))
        if chk.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")
        user.email = req.email

    if req.password:
        if len(req.password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        user.password_hash = hash_password(req.password)

    if req.is_active is not None:
        user.is_active = req.is_active

    if req.role_names is not None:
        roles_stmt = select(Role).where(Role.name.in_(req.role_names))
        roles_res = await db.execute(roles_stmt)
        user.roles = list(roles_res.scalars().all())

    if req.preferred_lang in ("en", "id"):
        user.preferred_lang = req.preferred_lang
    if req.preferred_theme in ("neon", "light"):
        user.preferred_theme = req.preferred_theme

    await db.commit()
    await record_audit_log(
        db, "USER_UPDATE", resource_type="users", resource_id=user.id,
        details={"username": user.username}, request=request
    )
    return {"success": True, "message": "User updated successfully"}


@router.delete("/{user_id}", dependencies=[Depends(require_permission("users:write"))])
async def delete_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete a user account."""
    stmt = select(User).options(selectinload(User.roles)).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent deleting the last Admin
    has_admin = any(r.name == "Admin" for r in user.roles)
    if has_admin:
        admin_count_stmt = select(func.count(User.id)).join(User.roles).where(Role.name == "Admin")
        count_res = await db.execute(admin_count_stmt)
        if count_res.scalar_one() <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the only remaining Administrator")

    username = user.username
    await db.delete(user)
    await db.commit()
    await record_audit_log(
        db, "USER_DELETE", resource_type="users", resource_id=user_id,
        details={"username": username}, request=request
    )
    return {"success": True, "message": "User deleted"}

