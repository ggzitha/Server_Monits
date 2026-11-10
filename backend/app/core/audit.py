import logging
from typing import Any, Dict, Optional
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models.audit import AuditLog

logger = logging.getLogger("server_monits.audit")


async def record_audit_log(
    db: AsyncSession,
    action: str,
    user_id: Optional[str] = None,
    resource_type: str = "",
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> AuditLog:
    """Record an audit trail event."""
    ip_address = ""
    user_agent = ""
    if request:
        # Check forward headers if behind proxy
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip_address = forwarded.split(",")[0].strip()
        elif request.client:
            ip_address = request.client.host
        user_agent = request.headers.get("user-agent", "")[:255]

    audit_entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(audit_entry)
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to write audit log: {e}")
        
    return audit_entry

