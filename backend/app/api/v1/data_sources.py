"""
data_sources.py - Data Sources Management & Test API
"""
import copy
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_db, require_permission
from backend.app.core.security import encrypt_secret, decrypt_secret, generate_secure_token
from backend.app.db.models.data_source import DataSource
from backend.app.services.http_poller import execute_safe_http_poll
from backend.app.services.mqtt_service import mqtt_service

router = APIRouter(prefix="/data-sources", tags=["data-sources"])

SENSITIVE_KEYS = {"password", "token", "secret", "auth_token", "api_key"}


def mask_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Mask sensitive fields in configuration dictionary."""
    if not config:
        return {}
    masked = copy.deepcopy(config)
    for k in list(masked.keys()):
        if any(sens in k.lower() for sens in SENSITIVE_KEYS) and masked[k]:
            masked[k] = "********"
    return masked


class DataSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    source_type: str = Field(..., pattern="^(mqtt|http_poll|webhook|manual_csv)$")
    config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class DataSourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class DataSourceTestDraft(BaseModel):
    source_type: str = Field(..., pattern="^(mqtt|http_poll|webhook|manual_csv)$")
    config: Dict[str, Any] = Field(default_factory=dict)


@router.get("", response_model=List[Dict[str, Any]])
async def list_data_sources(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission("settings:read")),
):
    """List all configured data sources with masked sensitive credentials."""
    stmt = select(DataSource).order_by(DataSource.created_at.desc())
    res = await db.execute(stmt)
    sources = res.scalars().all()

    return [
        {
            "id": s.id,
            "name": s.name,
            "source_type": s.source_type,
            "config": mask_config(s.config),
            "is_active": s.is_active,
            "last_polled_at": s.last_polled_at,
            "last_status": s.last_status,
            "last_error": s.last_error,
            "created_at": s.created_at,
        }
        for s in sources
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_data_source(
    data: DataSourceCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission("settings:write")),
):
    """Create a new data source with credentials encrypted at rest."""
    cfg = copy.deepcopy(data.config)

    # For webhook sources, ensure an ingestion token exists
    if data.source_type == "webhook" and not cfg.get("webhook_token"):
        cfg["webhook_token"] = generate_secure_token(24)

    # Encrypt sensitive credentials
    for k in list(cfg.keys()):
        if any(sens in k.lower() for sens in SENSITIVE_KEYS) and isinstance(cfg[k], str) and cfg[k]:
            cfg[k] = encrypt_secret(cfg[k])

    source = DataSource(
        name=data.name,
        source_type=data.source_type,
        config=cfg,
        is_active=data.is_active,
        last_status="idle",
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    return {
        "id": source.id,
        "name": source.name,
        "source_type": source.source_type,
        "config": mask_config(source.config),
        "is_active": source.is_active,
        "message": f"Data source '{source.name}' created successfully.",
    }


@router.get("/{source_id}")
async def get_data_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission("settings:read")),
):
    """Get single data source detail."""
    stmt = select(DataSource).where(DataSource.id == source_id)
    source = (await db.execute(stmt)).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")

    return {
        "id": source.id,
        "name": source.name,
        "source_type": source.source_type,
        "config": mask_config(source.config),
        "is_active": source.is_active,
        "last_polled_at": source.last_polled_at,
        "last_status": source.last_status,
        "last_error": source.last_error,
        "created_at": source.created_at,
    }


@router.put("/{source_id}")
async def update_data_source(
    source_id: str,
    data: DataSourceUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission("settings:write")),
):
    """Update an existing data source."""
    stmt = select(DataSource).where(DataSource.id == source_id)
    source = (await db.execute(stmt)).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")

    if data.name is not None:
        source.name = data.name
    if data.is_active is not None:
        source.is_active = data.is_active

    if data.config is not None:
        new_cfg = copy.deepcopy(data.config)
        old_cfg = source.config or {}

        # Preserve masked credentials if untouched
        for k in list(new_cfg.keys()):
            if any(sens in k.lower() for sens in SENSITIVE_KEYS) and new_cfg[k] == "********":
                new_cfg[k] = old_cfg.get(k, "")
            elif any(sens in k.lower() for sens in SENSITIVE_KEYS) and isinstance(new_cfg[k], str) and new_cfg[k]:
                new_cfg[k] = encrypt_secret(new_cfg[k])

        source.config = new_cfg

    await db.commit()
    await db.refresh(source)

    return {
        "id": source.id,
        "name": source.name,
        "source_type": source.source_type,
        "config": mask_config(source.config),
        "is_active": source.is_active,
    }


@router.delete("/{source_id}")
async def delete_data_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission("settings:write")),
):
    """Delete a data source."""
    stmt = select(DataSource).where(DataSource.id == source_id)
    source = (await db.execute(stmt)).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")

    await db.delete(source)
    await db.commit()
    return {"message": f"Data source '{source.name}' deleted successfully."}


async def _run_source_test(source_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Execute live test probe for a given source type and configuration."""
    if source_type == "http_poll":
        url = config.get("url")
        if not url:
            raise HTTPException(status_code=400, detail="Missing 'url' in configuration")
        headers = config.get("headers", {})
        json_path = config.get("json_path", "$")
        timeout = float(config.get("timeout_seconds", 5.0))
        allow_private = bool(config.get("allow_private_ranges", False))

        try:
            result = await execute_safe_http_poll(
                url=url,
                headers=headers,
                json_path=json_path,
                timeout_seconds=timeout,
                allow_private_ranges=allow_private,
            )
            return {
                "success": True,
                "message": f"HTTP Poll succeeded (Status {result['status_code']})",
                "sample_data": result["extracted_data"],
                "endpoint": result["url"],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    elif source_type == "mqtt":
        # Test connection or topic subscription
        topic = config.get("topic", "sensors/+/telemetry")
        res = await mqtt_service.test_connection(test_topic=topic)
        return res

    elif source_type == "webhook":
        token = config.get("webhook_token", "sample-token")
        webhook_url = f"/api/v1/telemetry/webhook/{token}"
        curl_example = (
            f"curl -X POST http://<server_host>{webhook_url} "
            f"-H 'Content-Type: application/json' "
            f"-d '{{\"sensor_id\": \"SN-01\", \"temperature\": 22.4, \"humidity\": 48.0}}'"
        )
        return {
            "success": True,
            "message": "Webhook endpoint is ready to receive POST requests.",
            "webhook_path": webhook_url,
            "curl_example": curl_example,
        }

    elif source_type == "manual_csv":
        return {
            "success": True,
            "message": "Manual/CSV data source active. Ready for batch imports.",
            "csv_template": "timestamp,sensor_id,temperature,humidity,battery\n2026-11-10T12:00:00Z,SN-01,21.5,45.2,3.6",
        }

    raise HTTPException(status_code=400, detail=f"Unsupported source type '{source_type}'")


@router.post("/{source_id}/test")
async def test_data_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission("settings:read")),
):
    """Test connection and fetch a sample reading from an existing data source."""
    stmt = select(DataSource).where(DataSource.id == source_id)
    source = (await db.execute(stmt)).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")

    # Decrypt sensitive credentials for testing
    cfg = copy.deepcopy(source.config or {})
    for k in list(cfg.keys()):
        if any(sens in k.lower() for sens in SENSITIVE_KEYS) and isinstance(cfg[k], str) and cfg[k]:
            try:
                cfg[k] = decrypt_secret(cfg[k])
            except Exception:
                pass

    res = await _run_source_test(source.source_type, cfg)
    source.last_status = "ok" if res.get("success") else "error"
    source.last_error = None if res.get("success") else res.get("error")
    await db.commit()

    return res


@router.post("/test-draft")
async def test_data_source_draft(
    data: DataSourceTestDraft,
    user=Depends(require_permission("settings:read")),
):
    """Test connection and probe sample reading for draft configuration before saving."""
    return await _run_source_test(data.source_type, data.config)

