"""
data_sources.py - Data Sources Management & Test API
"""
import copy
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
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
    source_type: str = Field(..., pattern="^(mysql|postgresql|sqlite|mqtt|http_poll|webhook|manual_csv)$")
    config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class DataSourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class DataSourceTestDraft(BaseModel):
    source_type: str = Field(..., pattern="^(mysql|postgresql|sqlite|mqtt|http_poll|webhook|manual_csv)$")
    config: Dict[str, Any] = Field(default_factory=dict)


class DataSourceQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    format: str = Field("time_series", pattern="^(time_series|table)$")
    hours_back: int = Field(24, ge=1, le=720)
    limit: int = Field(200, ge=1, le=1000)


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

    elif source_type in ("sqlite", "postgresql", "mysql"):
        try:
            probe_sql = "SELECT 1 AS ok"
            res = await _execute_sql_query(source_type, config, probe_sql, hours_back=24, limit=5)
            return {
                "success": True,
                "message": f"{source_type.upper()} connection succeeded ({res['execution_ms']} ms).",
                "sample_data": res["rows"],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    raise HTTPException(status_code=400, detail=f"Unsupported source type '{source_type}'")


def _validate_readonly_sql(raw_sql: str) -> str:
    """Ensure SQL query is strictly a single read-only SELECT statement."""
    sql = raw_sql.strip().rstrip(";")
    if not sql:
        raise HTTPException(status_code=400, detail="SQL query cannot be empty")
    if ";" in sql:
        raise HTTPException(status_code=400, detail="Multiple SQL statements are not permitted")
    if not re.match(r"^\s*(SELECT|WITH)\b", sql, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Only read-only SELECT / WITH queries are permitted")
    forbidden = re.search(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|GRANT|REVOKE|ATTACH|PRAGMA)\b",
        sql,
        re.IGNORECASE,
    )
    if forbidden:
        raise HTTPException(status_code=400, detail=f"Forbidden SQL keyword: {forbidden.group(1).upper()}")
    return sql


def _expand_grafana_macros(sql: str, hours_back: int = 24) -> str:
    """Expand Grafana time macros ($__timeFrom(), $__timeTo()) into ISO UTC timestamps."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours_back)
    sql = sql.replace("$__timeFrom()", f"'{start.strftime('%Y-%m-%d %H:%M:%S')}'")
    sql = sql.replace("$__timeTo()", f"'{now.strftime('%Y-%m-%d %H:%M:%S')}'")
    return sql


async def _execute_sql_query(
    source_type: str,
    config: Dict[str, Any],
    raw_sql: str,
    hours_back: int = 24,
    limit: int = 200,
) -> Dict[str, Any]:
    """Execute a read-only SQL query against SQLite, PostgreSQL, or MySQL."""
    sql = _expand_grafana_macros(_validate_readonly_sql(raw_sql), hours_back=hours_back)
    t0 = time.perf_counter()
    columns: List[str] = []
    rows: List[Dict[str, Any]] = []

    if source_type == "sqlite":
        db_path = config.get("database") or config.get("path") or "server_monits_dev.db"
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute(sql)
            fetched = cur.fetchmany(limit)
            columns = [desc[0] for desc in (cur.description or [])]
            for r in fetched:
                rows.append({k: r[k] for k in columns})
        finally:
            conn.close()

    elif source_type == "postgresql":
        import asyncpg
        conn = await asyncpg.connect(
            host=config.get("host", "127.0.0.1"),
            port=int(config.get("port", 5432)),
            user=config.get("username", "postgres"),
            password=config.get("password", ""),
            database=config.get("database", "postgres"),
            timeout=5.0,
        )
        try:
            records = await conn.fetch(sql)
            if records:
                columns = list(records[0].keys())
                for rec in records[:limit]:
                    rows.append({k: (rec[k].isoformat() if hasattr(rec[k], "isoformat") else rec[k]) for k in columns})
        finally:
            await conn.close()

    elif source_type == "mysql":
        try:
            import aiomysql
            conn = await aiomysql.connect(
                host=config.get("host", "127.0.0.1"),
                port=int(config.get("port", 3306)),
                user=config.get("username", "root"),
                password=config.get("password", ""),
                db=config.get("database", ""),
                connect_timeout=5,
            )
            try:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(sql)
                    fetched = await cur.fetchmany(limit)
                    if fetched:
                        columns = list(fetched[0].keys())
                        for r in fetched:
                            rows.append({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()})
            finally:
                conn.close()
        except ImportError:
            try:
                import pymysql
                conn = pymysql.connect(
                    host=config.get("host", "127.0.0.1"),
                    port=int(config.get("port", 3306)),
                    user=config.get("username", "root"),
                    password=config.get("password", ""),
                    database=config.get("database", ""),
                    connect_timeout=5,
                    cursorclass=pymysql.cursors.DictCursor,
                )
                try:
                    with conn.cursor() as cur:
                        cur.execute(sql)
                        fetched = cur.fetchmany(limit)
                        if fetched:
                            columns = list(fetched[0].keys())
                            for r in fetched:
                                rows.append({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()})
                finally:
                    conn.close()
            except ImportError:
                raise HTTPException(
                    status_code=400,
                    detail="MySQL driver (pymysql or aiomysql) is not installed in this Python environment. Install pymysql to query external MySQL servers.",
                )

    else:
        raise HTTPException(status_code=400, detail=f"SQL Query Runner is for SQLite/PostgreSQL/MySQL sources, got '{source_type}'")

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    return {
        "success": True,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "execution_ms": elapsed_ms,
    }


@router.post("/{source_id}/query")
async def query_data_source(
    source_id: str,
    req: DataSourceQueryRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission("settings:read")),
):
    """Execute a Grafana-style read-only SQL query against a saved SQL data source."""
    stmt = select(DataSource).where(DataSource.id == source_id)
    source = (await db.execute(stmt)).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")

    cfg = copy.deepcopy(source.config or {})
    for k in list(cfg.keys()):
        if any(sens in k.lower() for sens in SENSITIVE_KEYS) and isinstance(cfg[k], str) and cfg[k]:
            try:
                cfg[k] = decrypt_secret(cfg[k])
            except Exception:
                pass

    res = await _execute_sql_query(
        source.source_type, cfg, req.query, hours_back=req.hours_back, limit=req.limit
    )
    res["format"] = req.format
    return res


@router.post("/query-draft")
async def query_draft_data_source(
    source_type: str = Query(..., pattern="^(sqlite|postgresql|mysql)$"),
    req: DataSourceQueryRequest = ...,
    database: str = Query("server_monits_dev.db"),
    host: str = Query("127.0.0.1"),
    port: int = Query(5432),
    username: str = Query(""),
    password: str = Query(""),
    user=Depends(require_permission("settings:read")),
):
    """Run an ad-hoc Grafana-style SQL query against draft connection settings."""
    cfg = {
        "database": database,
        "host": host,
        "port": port,
        "username": username,
        "password": password,
    }
    res = await _execute_sql_query(
        source_type, cfg, req.query, hours_back=req.hours_back, limit=req.limit
    )
    res["format"] = req.format
    return res


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

