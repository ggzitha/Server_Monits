from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_db, require_permission
from backend.app.core.rbac import PERMISSIONS
from backend.app.db.models.user import Role

router = APIRouter(prefix="/roles", tags=["roles"])


class CreateRoleRequest(BaseModel):
    name: str
    description: str = ""
    permissions: List[str]


class UpdateRoleRequest(BaseModel):
    description: str = ""
    permissions: List[str]


@router.get("", dependencies=[Depends(require_permission("roles:read"))])
async def list_roles(db: AsyncSession = Depends(get_db)):
    """List all system and custom roles along with the permissions dictionary."""
    stmt = select(Role).order_by(Role.is_system.desc(), Role.name.asc())
    res = await db.execute(stmt)
    roles = res.scalars().all()

    return {
        "roles": [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "permissions": r.permissions,
                "is_system": r.is_system,
            }
            for r in roles
        ],
        "available_permissions": PERMISSIONS,
    }


@router.post("", dependencies=[Depends(require_permission("roles:write"))])
async def create_role(req: CreateRoleRequest, db: AsyncSession = Depends(get_db)):
    """Create a new custom role."""
    chk = await db.execute(select(Role).where(Role.name == req.name))
    if chk.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Role name already exists")

    new_role = Role(
        name=req.name,
        description=req.description,
        permissions=req.permissions,
        is_system=False,
    )
    db.add(new_role)
    await db.commit()
    await db.refresh(new_role)

    return {
        "id": new_role.id,
        "name": new_role.name,
        "description": new_role.description,
        "permissions": new_role.permissions,
        "is_system": False,
    }


@router.put("/{role_id}", dependencies=[Depends(require_permission("roles:write"))])
async def update_role(role_id: str, req: UpdateRoleRequest, db: AsyncSession = Depends(get_db)):
    """Update permissions or description of a custom role."""
    stmt = select(Role).where(Role.id == role_id)
    res = await db.execute(stmt)
    role = res.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
        
    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot modify built-in system role")

    role.description = req.description
    role.permissions = req.permissions
    await db.commit()
    return {"success": True, "message": "Role updated"}

