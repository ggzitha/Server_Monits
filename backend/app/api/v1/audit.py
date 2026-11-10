from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_db, require_permission
from backend.app.db.models.audit import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", dependencies=[Depends(require_permission("audit:read"))])
async def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    action: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve audit trail logs with filtering and pagination."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        stmt = stmt.where(AuditLog.action == action)

    count_stmt = select(func.count(AuditLog.id))
    if action:
        count_stmt = count_stmt.where(AuditLog.action == action)
        
    total_res = await db.execute(count_stmt)
    total = total_res.scalar_one()

    res = await db.execute(stmt.offset(skip).limit(limit))
    logs = res.scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": l.id,
                "user_id": l.user_id,
                "action": l.action,
                "resource_type": l.resource_type,
                "resource_id": l.resource_id,
                "details": l.details,
                "ip_address": l.ip_address,
                "created_at": l.created_at,
            }
            for l in logs
        ],
    }

