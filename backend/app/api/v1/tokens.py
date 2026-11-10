from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user, get_db
from backend.app.core.security import generate_secure_token, hash_token
from backend.app.db.models.auth_tokens import ApiToken
from backend.app.db.models.user import User

router = APIRouter(prefix="/tokens", tags=["tokens"])


class CreateTokenRequest(BaseModel):
    name: str
    scopes: List[str] = ["*"]
    expires_in_days: Optional[int] = 365


@router.get("")
async def list_tokens(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all API tokens belonging to the authenticated user."""
    stmt = select(ApiToken).where(ApiToken.user_id == current_user.id).order_by(ApiToken.created_at.desc())
    res = await db.execute(stmt)
    tokens = res.scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "scopes": t.scopes,
            "expires_at": t.expires_at,
            "last_used_at": t.last_used_at,
            "created_at": t.created_at,
        }
        for t in tokens
    ]


@router.post("")
async def create_token(
    req: CreateTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new scoped API token."""
    raw_token = "monit_" + generate_secure_token(32)
    token_hashed = hash_token(raw_token)

    expires_at = None
    if req.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=req.expires_in_days)

    token_obj = ApiToken(
        user_id=current_user.id,
        name=req.name,
        token_hash=token_hashed,
        scopes=req.scopes,
        expires_at=expires_at,
    )
    db.add(token_obj)
    await db.commit()
    await db.refresh(token_obj)

    return {
        "id": token_obj.id,
        "name": token_obj.name,
        "token": raw_token,  # Shown only once
        "scopes": token_obj.scopes,
        "expires_at": token_obj.expires_at,
        "message": "Token generated. Make sure to copy it now; you will not be able to see it again.",
    }


@router.delete("/{token_id}")
async def revoke_token(
    token_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke and delete an API token."""
    stmt = select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == current_user.id)
    res = await db.execute(stmt)
    token_obj = res.scalar_one_or_none()

    if not token_obj:
        raise HTTPException(status_code=404, detail="API token not found")

    await db.delete(token_obj)
    await db.commit()
    return {"success": True, "message": "API token revoked"}

