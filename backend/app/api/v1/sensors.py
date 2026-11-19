"""
sensors.py - Database-Backed Sensor Telemetry & Virtual Device Control API
Provides direct DB sensor readings, historical sparkline time-series, and virtual light/switch persistence
completely detached from Home Assistant.
"""
import copy
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user, get_db
from backend.app.api.v1.data_sources import SENSITIVE_KEYS, _execute_sql_query
from backend.app.core.security import decrypt_secret
from backend.app.db.models.data_source import DataSource
from backend.app.db.models.floor_plan import FloorPlan
from backend.app.db.models.sensor import Sensor
from backend.app.db.models.system_config import SystemConfig
from backend.app.db.models.telemetry import TelemetryReading
from backend.app.services.ingestion import process_telemetry_reading
from backend.app.services.notifier import notifier

router = APIRouter(prefix="/sensors", tags=["sensors"])

DEFAULT_DB_SENSORS = [
    {
        "identifier": "server_alpha_env",
        "name": "Server Room Alpha Thermohygrograph",
        "sensor_type": "thermohygrometer",
        "current_temperature": 21.4,
        "current_humidity": 44.5,
        "battery_level": 98.0,
        "status": "online",
        "metadata_json": {"area_id": "server_alpha", "power_kw": 42.8, "wifi_dbm": -42},
    },
    {
        "identifier": "noc_env",
        "name": "NOC Operations Center Sensor",
        "sensor_type": "thermohygrometer",
        "current_temperature": 22.8,
        "current_humidity": 46.0,
        "battery_level": 95.0,
        "status": "online",
        "metadata_json": {"area_id": "noc", "power_kw": 8.4, "wifi_dbm": -38},
    },
    {
        "identifier": "ups_env",
        "name": "UPS & Power Room Sensor",
        "sensor_type": "thermohygrometer",
        "current_temperature": 24.6,
        "current_humidity": 41.2,
        "battery_level": 100.0,
        "status": "online",
        "metadata_json": {"area_id": "ups", "power_kw": 68.4, "wifi_dbm": -55},
    },
    {
        "identifier": "battery_env",
        "name": "Battery Storage Room Sensor",
        "sensor_type": "thermohygrometer",
        "current_temperature": 23.1,
        "current_humidity": 39.8,
        "battery_level": 92.0,
        "status": "online",
        "metadata_json": {"area_id": "battery", "power_kw": 12.0, "wifi_dbm": -61},
    },
    {
        "identifier": "meet_me_env",
        "name": "Telecom Meet-Me Room Sensor",
        "sensor_type": "thermohygrometer",
        "current_temperature": 20.9,
        "current_humidity": 43.0,
        "battery_level": 97.0,
        "status": "online",
        "metadata_json": {"area_id": "meet_me", "power_kw": 15.2, "wifi_dbm": -45},
    },
    {
        "identifier": "server_beta_env",
        "name": "Server Room Beta Thermohygrograph",
        "sensor_type": "thermohygrometer",
        "current_temperature": 21.8,
        "current_humidity": 45.1,
        "battery_level": 96.0,
        "status": "online",
        "metadata_json": {"area_id": "server_beta", "power_kw": 36.5, "wifi_dbm": -44},
    },
    {
        "identifier": "network_core_env",
        "name": "Network Core Room Sensor",
        "sensor_type": "thermohygrometer",
        "current_temperature": 20.5,
        "current_humidity": 42.3,
        "battery_level": 99.0,
        "status": "online",
        "metadata_json": {"area_id": "network_core", "power_kw": 24.1, "wifi_dbm": -36},
    },
    {
        "identifier": "security_env",
        "name": "Security & Access Center Sensor",
        "sensor_type": "thermohygrometer",
        "current_temperature": 22.4,
        "current_humidity": 47.0,
        "battery_level": 94.0,
        "status": "online",
        "metadata_json": {"area_id": "security", "power_kw": 4.2, "wifi_dbm": -48},
    },
]


async def ensure_default_sensors(db: AsyncSession) -> List[Sensor]:
    """Ensure the database has initial Data Center room sensors and telemetry history."""
    res = await db.execute(select(Sensor).order_by(Sensor.identifier))
    sensors = list(res.scalars().all())
    if sensors:
        return sensors

    now = datetime.now(timezone.utc)
    seeded: List[Sensor] = []
    for item in DEFAULT_DB_SENSORS:
        s = Sensor(
            identifier=item["identifier"],
            name=item["name"],
            sensor_type=item["sensor_type"],
            current_temperature=item["current_temperature"],
            current_humidity=item["current_humidity"],
            battery_level=item["battery_level"],
            status=item["status"],
            last_seen_at=now,
            is_discovered=False,
            metadata_json=item["metadata_json"],
        )
        db.add(s)
        await db.flush()

        # Seed 12 historical readings over the last 6 hours for sparkline charts
        base_t = item["current_temperature"]
        base_h = item["current_humidity"]
        for step in range(12):
            offset_min = (11 - step) * 30
            ts = now - timedelta(minutes=offset_min)
            wave = ((step % 4) - 1.5) * 0.35
            db.add(
                TelemetryReading(
                    sensor_id=s.id,
                    timestamp=ts,
                    temperature=round(base_t + wave, 2),
                    humidity=round(base_h - wave * 1.2, 2),
                    raw_data=item["metadata_json"],
                )
            )
        seeded.append(s)

    await db.commit()
    return seeded


class DirectReadingInput(BaseModel):
    identifier: str = Field(..., min_length=1, max_length=100)
    name: Optional[str] = None
    sensor_type: Optional[str] = None
    area_id: Optional[str] = None
    floor_id: Optional[str] = None
    placement_x: Optional[float] = None
    placement_z: Optional[float] = None
    placement_y: Optional[float] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    power_kw: Optional[float] = None
    amperes: Optional[float] = None
    volts: Optional[float] = None
    wifi_dbm: Optional[float] = None
    battery_level: Optional[float] = None
    data_source_id: Optional[str] = None
    sql_query: Optional[str] = None
    sql_query_humidity: Optional[str] = None
    grafana_link_enabled: Optional[bool] = None
    grafana_new_tab: Optional[bool] = None
    grafana_url: Optional[str] = None


class VirtualStateUpdate(BaseModel):
    entity_id: str = Field(..., min_length=1, max_length=150)
    state: str = Field(..., min_length=1, max_length=50)
    attributes: Dict[str, Any] = Field(default_factory=dict)


class BuildingSavePayload(BaseModel):
    building: Dict[str, Any]
    name: Optional[str] = "Main Server Facility"
    site: Optional[str] = "Datacenter Alpha"
    areas: Optional[Dict[str, Any]] = None
    snapshots: Optional[List[Dict[str, Any]]] = None
    revision: Optional[int] = None


@router.get("")
async def list_sensors(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return all sensors stored in the database (seeding initial facility sensors if empty)."""
    sensors = await ensure_default_sensors(db)
    out = []
    for s in sensors:
        meta = s.metadata_json or {}
        out.append(
            {
                "id": s.id,
                "identifier": s.identifier,
                "name": s.name,
                "sensor_type": s.sensor_type,
                "area_id": meta.get("area_id", "server_alpha"),
                "floor_id": meta.get("floor_id", "ground"),
                "placement_x": meta.get("placement_x"),
                "placement_z": meta.get("placement_z"),
                "placement_y": meta.get("placement_y"),
                "current_temperature": s.current_temperature,
                "current_humidity": s.current_humidity,
                "power_kw": meta.get("power_kw"),
                "amperes": meta.get("amperes"),
                "volts": meta.get("volts"),
                "wifi_dbm": meta.get("wifi_dbm"),
                "data_source_id": meta.get("data_source_id"),
                "sql_query": meta.get("sql_query"),
                "sql_query_humidity": meta.get("sql_query_humidity"),
                "grafana_link_enabled": bool(meta.get("grafana_link_enabled", False)),
                "grafana_new_tab": bool(meta.get("grafana_new_tab", True)),
                "grafana_url": meta.get("grafana_url", ""),
                "battery_level": s.battery_level,
                "status": s.status,
                "temp_max_warning": s.temp_max_warning,
                "temp_max_critical": s.temp_max_critical,
                "humidity_max_warning": s.humidity_max_warning,
                "humidity_max_critical": s.humidity_max_critical,
                "last_seen_at": s.last_seen_at.isoformat() if s.last_seen_at else None,
            }
        )
    return out


def _extract_metrics_from_row(row: Dict[str, Any], sensor_type: str) -> Dict[str, float]:
    """Map SQL result row columns to sensor metrics by column name or sensor_type fallback."""
    out: Dict[str, float] = {}
    numeric_cols: List[tuple[str, float]] = []
    for k, v in row.items():
        kl = str(k).strip().lower()
        if kl in ("time", "date_time", "datetime", "timestamp", "recorded_at", "ts"):
            continue
        try:
            num = float(v)
        except (TypeError, ValueError):
            continue
        numeric_cols.append((kl, num))
        if any(tok in kl for tok in ("temp", "suhu")):
            out["temperature"] = num
        elif any(tok in kl for tok in ("hum", "rh", "kelembaban")):
            out["humidity"] = num
        elif any(tok in kl for tok in ("power", "kw", "watt")):
            out["power_kw"] = num
        elif any(tok in kl for tok in ("amp", "current", "arus")):
            out["amperes"] = num
        elif any(tok in kl for tok in ("volt", "tegangan")):
            out["volts"] = num
        elif "batt" in kl:
            out["battery_level"] = num

    if not out and numeric_cols:
        primary_val = numeric_cols[0][1]
        st = (sensor_type or "thermohygrometer").lower()
        if st in ("thermohygrometer", "thermometer"):
            out["temperature"] = primary_val
            if st == "thermohygrometer" and len(numeric_cols) > 1:
                out["humidity"] = numeric_cols[1][1]
        elif st == "hygrometer":
            out["humidity"] = primary_val
        elif st == "power_meter":
            out["power_kw"] = primary_val
        elif st == "ammeter":
            out["amperes"] = primary_val
        elif st == "voltmeter":
            out["volts"] = primary_val
    return out


def _pick_latest_row(rows: List[Dict[str, Any]], raw_sql: str) -> Dict[str, Any]:
    """Return the newest row whether SQL used ORDER BY ... DESC or ASC."""
    if len(rows) <= 1:
        return rows[0]
    if re.search(r"\bORDER\s+BY\b[^;]*\bDESC\b", raw_sql, re.IGNORECASE):
        return rows[0]
    return rows[-1]


def _extract_row_timestamp(row: Dict[str, Any]) -> Optional[str]:
    """Extract ISO-like timestamp string from common SQL time columns."""
    for k, v in row.items():
        if str(k).strip().lower() in ("time", "date_time", "datetime", "timestamp", "recorded_at", "ts"):
            if v is not None:
                return v.isoformat() if hasattr(v, "isoformat") else str(v)
    return None


def _decrypt_source_config(source: DataSource) -> Dict[str, Any]:
    cfg = copy.deepcopy(source.config or {})
    for k in list(cfg.keys()):
        if any(sens in k.lower() for sens in SENSITIVE_KEYS) and isinstance(cfg[k], str) and cfg[k]:
            try:
                cfg[k] = decrypt_secret(cfg[k])
            except Exception:
                pass
    return cfg


async def _sync_sensor_from_datasource(db: AsyncSession, sensor: Sensor) -> Dict[str, Any]:
    """Execute a sensor's bound SQL query against its configured DataSource without duplicating readings."""
    meta = dict(sensor.metadata_json or {})
    ds_id = meta.get("data_source_id")
    sql_query = (meta.get("sql_query") or "").strip()
    sql_query_hum = (meta.get("sql_query_humidity") or "").strip()
    if not ds_id or (not sql_query and not sql_query_hum):
        return {"ok": False, "skipped": True, "reason": "No data_source_id or sql_query"}

    source = (await db.execute(select(DataSource).where(DataSource.id == str(ds_id)))).scalar_one_or_none()
    if not source:
        return {"ok": False, "error": f"Data source '{ds_id}' not found"}

    cfg = _decrypt_source_config(source)
    metrics: Dict[str, float] = {}
    total_rows = 0
    exec_ms = 0.0

    if sql_query:
        try:
            res = await _execute_sql_query(source.source_type, cfg, sql_query, hours_back=24, limit=5000)
        except HTTPException as exc:
            return {"ok": False, "error": str(exc.detail)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        rows = res.get("rows") or []
        total_rows = len(rows)
        exec_ms = res.get("execution_ms") or 0.0
        if rows:
            latest = _pick_latest_row(rows, sql_query)
            metrics.update(_extract_metrics_from_row(latest, sensor.sensor_type))

    if sql_query_hum:
        try:
            res_h = await _execute_sql_query(source.source_type, cfg, sql_query_hum, hours_back=24, limit=5000)
            rows_h = res_h.get("rows") or []
            if rows_h:
                latest_h = _pick_latest_row(rows_h, sql_query_hum)
                m_h = _extract_metrics_from_row(latest_h, "hygrometer")
                if "humidity" in m_h:
                    metrics["humidity"] = m_h["humidity"]
        except Exception:
            pass

    if not metrics:
        return {"ok": False, "error": "SQL query returned 0 usable rows", "row_count": total_rows}

    if "temperature" in metrics:
        sensor.current_temperature = round(metrics["temperature"], 2)
    if "humidity" in metrics:
        sensor.current_humidity = round(metrics["humidity"], 2)
    if "power_kw" in metrics:
        meta["power_kw"] = round(metrics["power_kw"], 2)
    if "amperes" in metrics:
        meta["amperes"] = round(metrics["amperes"], 2)
    if "volts" in metrics:
        meta["volts"] = round(metrics["volts"], 2)
    if "battery_level" in metrics:
        sensor.battery_level = round(metrics["battery_level"], 1)
    sensor.metadata_json = meta
    sensor.last_seen_at = datetime.now(timezone.utc)
    sensor.status = "online"
    await db.commit()
    return {"ok": True, "row_count": total_rows, "metrics": metrics, "execution_ms": exec_ms}


@router.post("/readings", status_code=status.HTTP_200_OK)
async def push_sensor_reading(
    data: DirectReadingInput,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Directly update/record a sensor reading; skip local TelemetryReading storage when bound to external SQL."""
    is_external_sql = bool(data.data_source_id) and bool((data.sql_query or "").strip() or (data.sql_query_humidity or "").strip())
    stmt = select(Sensor).where(Sensor.identifier == data.identifier)
    sensor = (await db.execute(stmt)).scalar_one_or_none()

    if is_external_sql:
        if not sensor:
            sensor = Sensor(
                identifier=data.identifier,
                name=data.name or data.identifier,
                sensor_type=data.sensor_type or "thermohygrometer",
                current_temperature=data.temperature,
                current_humidity=data.humidity,
                battery_level=data.battery_level,
                status="online",
                metadata_json={},
            )
            db.add(sensor)
            await db.flush()
        result: Dict[str, Any] = {"status": "ok", "identifier": data.identifier}
    else:
        payload: Dict[str, Any] = {
            "identifier": data.identifier,
            "temperature": data.temperature,
            "humidity": data.humidity,
            "battery_level": data.battery_level,
        }
        if data.power_kw is not None:
            payload["power_kw"] = data.power_kw
        if data.wifi_dbm is not None:
            payload["wifi_dbm"] = data.wifi_dbm
        if data.area_id is not None:
            payload["area_id"] = data.area_id
        result = await process_telemetry_reading(db, payload)
        sensor = (await db.execute(stmt)).scalar_one_or_none()
    if sensor:
        if data.name:
            sensor.name = data.name
        if data.sensor_type:
            sensor.sensor_type = data.sensor_type
        meta = dict(sensor.metadata_json or {})
        if data.area_id:
            meta["area_id"] = data.area_id
        if data.floor_id:
            meta["floor_id"] = data.floor_id
        if data.placement_x is not None:
            meta["placement_x"] = round(float(data.placement_x), 2)
        if data.placement_z is not None:
            meta["placement_z"] = round(float(data.placement_z), 2)
        if data.placement_y is not None:
            meta["placement_y"] = round(float(data.placement_y), 2)
        if data.power_kw is not None:
            meta["power_kw"] = round(float(data.power_kw), 2)
        if data.amperes is not None:
            meta["amperes"] = round(float(data.amperes), 2)
        if data.volts is not None:
            meta["volts"] = round(float(data.volts), 2)
        if data.wifi_dbm is not None:
            meta["wifi_dbm"] = round(float(data.wifi_dbm), 1)
        if data.data_source_id is not None:
            if data.data_source_id == "":
                meta.pop("data_source_id", None)
            else:
                meta["data_source_id"] = data.data_source_id
        if data.sql_query is not None:
            if data.sql_query.strip() == "":
                meta.pop("sql_query", None)
            else:
                meta["sql_query"] = data.sql_query
        if data.sql_query_humidity is not None:
            if data.sql_query_humidity.strip() == "":
                meta.pop("sql_query_humidity", None)
            else:
                meta["sql_query_humidity"] = data.sql_query_humidity
        if data.grafana_link_enabled is not None:
            meta["grafana_link_enabled"] = bool(data.grafana_link_enabled)
        if data.grafana_new_tab is not None:
            meta["grafana_new_tab"] = bool(data.grafana_new_tab)
        if data.grafana_url is not None:
            meta["grafana_url"] = data.grafana_url.strip()
        sensor.metadata_json = meta
        await db.commit()

        sql_sync = None
        if meta.get("data_source_id") and (meta.get("sql_query") or meta.get("sql_query_humidity")):
            sql_sync = await _sync_sensor_from_datasource(db, sensor)
            await db.refresh(sensor)
            meta = dict(sensor.metadata_json or {})

        # Force broadcast to all connected 3D views
        await notifier.broadcast_telemetry(
            sensor.identifier,
            {
                "identifier": sensor.identifier,
                "sensor_name": sensor.name,
                "sensor_type": sensor.sensor_type,
                "area_id": meta.get("area_id", "server_alpha"),
                "floor_id": meta.get("floor_id", "ground"),
                "placement_x": meta.get("placement_x"),
                "placement_z": meta.get("placement_z"),
                "placement_y": meta.get("placement_y"),
                "temperature": sensor.current_temperature,
                "humidity": sensor.current_humidity,
                "power_kw": meta.get("power_kw"),
                "amperes": meta.get("amperes"),
                "volts": meta.get("volts"),
                "wifi_dbm": meta.get("wifi_dbm"),
                "status": sensor.status,
            },
            force=True,
        )

    return {
        **result,
        "name": sensor.name if sensor else data.name,
        "sensor_type": sensor.sensor_type if sensor else data.sensor_type,
        "temperature": sensor.current_temperature if sensor else data.temperature,
        "humidity": sensor.current_humidity if sensor else data.humidity,
        "power_kw": (sensor.metadata_json or {}).get("power_kw") if sensor else data.power_kw,
        "amperes": (sensor.metadata_json or {}).get("amperes") if sensor else data.amperes,
        "volts": (sensor.metadata_json or {}).get("volts") if sensor else data.volts,
        "wifi_dbm": data.wifi_dbm,
        "area_id": data.area_id,
        "floor_id": data.floor_id,
        "placement_x": data.placement_x,
        "placement_z": data.placement_z,
        "placement_y": data.placement_y,
        "sql_sync": sql_sync if sensor else None,
    }


@router.post("/sync-sql")
async def sync_all_sql_sensors(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Execute SQL queries for all sensors bound to an external Data Source."""
    sensors = (await db.execute(select(Sensor))).scalars().all()
    results = {}
    for s in sensors:
        meta = s.metadata_json or {}
        if meta.get("data_source_id") and (meta.get("sql_query") or meta.get("sql_query_humidity")):
            results[s.identifier] = await _sync_sensor_from_datasource(db, s)
    return {"synced": len(results), "results": results}


@router.delete("/{identifier}")
async def delete_sensor_by_identifier(
    identifier: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Remove a custom sensor by identifier from the database."""
    stmt = select(Sensor).where((Sensor.identifier == identifier) | (Sensor.id == identifier))
    sensor = (await db.execute(stmt)).scalar_one_or_none()
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    await db.delete(sensor)
    await db.commit()
    return {"status": "deleted", "identifier": identifier}


@router.get("/building")
async def get_saved_3d_building(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Fetch the active persisted 3D building state from the database."""
    res = await db.execute(
        select(SystemConfig).where(SystemConfig.key == "active_3d_building")
    )
    cfg = res.scalar_one_or_none()
    if cfg and cfg.value:
        try:
            parsed = json.loads(cfg.value)
            if isinstance(parsed, dict) and parsed.get("building") and isinstance(parsed["building"].get("floors"), list):
                return {
                    "saved": True,
                    "building": parsed["building"],
                    "name": parsed.get("name", "Main Server Facility"),
                    "site": parsed.get("site", "Datacenter Alpha"),
                    "areas": parsed.get("areas"),
                    "snapshots": parsed.get("snapshots"),
                    "revision": parsed.get("revision", 1),
                    "updated_at": parsed.get("updated_at"),
                }
        except Exception:
            pass

    # Fallback: check most recently updated FloorPlan row if present
    fp_res = await db.execute(
        select(FloorPlan).order_by(FloorPlan.updated_at.desc(), FloorPlan.created_at.desc())
    )
    fp = fp_res.scalars().first()
    if fp and isinstance(fp.metadata_json, dict) and isinstance(fp.metadata_json.get("floors"), list):
        # Only use FloorPlan row if it has rooms, walls, or furniture
        has_content = any(
            len(f.get("rooms", [])) > 0 or len(f.get("walls", [])) > 0 or len(f.get("furniture", [])) > 0
            for f in fp.metadata_json.get("floors", [])
        )
        if has_content:
            return {
                "saved": True,
                "building": fp.metadata_json,
                "name": fp.name,
                "site": fp.site_name,
                "areas": None,
                "snapshots": None,
                "revision": 1,
                "updated_at": fp.updated_at.isoformat() if fp.updated_at else None,
            }

    return {"saved": False, "building": None}


@router.post("/building")
async def save_3d_building(
    payload: BuildingSavePayload,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Persist the active 3D building layout into both SystemConfig and FloorPlan tables."""
    now_iso = datetime.now(timezone.utc).isoformat()
    record = {
        "building": payload.building,
        "name": payload.name or "Main Server Facility",
        "site": payload.site or "Datacenter Alpha",
        "areas": payload.areas,
        "snapshots": payload.snapshots,
        "revision": payload.revision or 1,
        "updated_at": now_iso,
    }

    res = await db.execute(
        select(SystemConfig).where(SystemConfig.key == "active_3d_building")
    )
    cfg = res.scalar_one_or_none()
    if not cfg:
        cfg = SystemConfig(
            key="active_3d_building",
            value=json.dumps(record),
        )
        db.add(cfg)
    else:
        cfg.value = json.dumps(record)

    # Also keep primary FloorPlan row synchronized
    fp_res = await db.execute(
        select(FloorPlan).order_by(FloorPlan.updated_at.desc(), FloorPlan.created_at.desc())
    )
    fp = fp_res.scalars().first()
    if fp:
        fp.name = payload.name or fp.name
        fp.site_name = payload.site or fp.site_name
        fp.metadata_json = payload.building
    else:
        fp = FloorPlan(
            name=payload.name or "Main Server Facility",
            site_name=payload.site or "Datacenter Alpha",
            level_index=0,
            grid_size_meters=0.5,
            scale_ratio=1.0,
            metadata_json=payload.building,
        )
        db.add(fp)

    await db.commit()
    return {
        "status": "saved",
        "revision": record["revision"],
        "updated_at": now_iso,
        "plan_id": fp.id,
    }


@router.get("/{identifier}/history")
async def get_sensor_history(
    identifier: str,
    limit: int = 24,
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Fetch recent time-series telemetry readings from DB for sparklines and history graphs."""
    stmt = select(Sensor).where(
        (Sensor.identifier == identifier) | (Sensor.id == identifier)
    )
    sensor = (await db.execute(stmt)).scalar_one_or_none()
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    meta = sensor.metadata_json or {}
    ds_id = meta.get("data_source_id")
    sql_query = (meta.get("sql_query") or "").strip()
    sql_query_hum = (meta.get("sql_query_humidity") or "").strip()

    if ds_id and (sql_query or sql_query_hum):
        source = (await db.execute(select(DataSource).where(DataSource.id == str(ds_id)))).scalar_one_or_none()
        if source:
            cfg = _decrypt_source_config(source)
            readings_by_ts: Dict[str, Dict[str, Any]] = {}
            ordered_readings: List[Dict[str, Any]] = []
            max_rows = min(max(limit, 24), 2500)

            if sql_query:
                hist_sql = re.sub(r"\s+LIMIT\s+1\s*;?\s*$", "", sql_query.strip(), flags=re.IGNORECASE)
                try:
                    res = await _execute_sql_query(source.source_type, cfg, hist_sql, hours_back=hours, limit=25000)
                    raw_rows = res.get("rows") or []
                    if re.search(r"\bORDER\s+BY\b[^;]*\bDESC\b", hist_sql, re.IGNORECASE):
                        raw_rows = list(reversed(raw_rows))
                    for r in raw_rows:
                        ts = _extract_row_timestamp(r)
                        m = _extract_metrics_from_row(r, sensor.sensor_type)
                        entry = {
                            "timestamp": ts,
                            "temperature": m.get("temperature"),
                            "humidity": m.get("humidity"),
                            "raw_data": {k: v for k, v in m.items() if k not in ("temperature", "humidity")},
                        }
                        ordered_readings.append(entry)
                        if ts:
                            readings_by_ts[ts] = entry
                except Exception:
                    pass

            if sql_query_hum:
                hist_sql_h = re.sub(r"\s+LIMIT\s+1\s*;?\s*$", "", sql_query_hum.strip(), flags=re.IGNORECASE)
                try:
                    res_h = await _execute_sql_query(source.source_type, cfg, hist_sql_h, hours_back=hours, limit=25000)
                    raw_rows_h = res_h.get("rows") or []
                    if re.search(r"\bORDER\s+BY\b[^;]*\bDESC\b", hist_sql_h, re.IGNORECASE):
                        raw_rows_h = list(reversed(raw_rows_h))
                    for idx_h, r in enumerate(raw_rows_h):
                        ts = _extract_row_timestamp(r)
                        m_h = _extract_metrics_from_row(r, "hygrometer")
                        hum_val = m_h.get("humidity")
                        if ts and ts in readings_by_ts:
                            readings_by_ts[ts]["humidity"] = hum_val
                        elif idx_h < len(ordered_readings):
                            ordered_readings[idx_h]["humidity"] = hum_val
                        else:
                            ordered_readings.append({"timestamp": ts, "temperature": None, "humidity": hum_val, "raw_data": {}})
                except Exception:
                    pass

            if ordered_readings:
                # Evenly downsample across the full time window so the entire 24h range is preserved
                if len(ordered_readings) > max_rows:
                    step = (len(ordered_readings) - 1) / float(max_rows - 1)
                    sampled = [ordered_readings[round(i * step)] for i in range(max_rows)]
                else:
                    sampled = ordered_readings
                return {
                    "sensor_id": sensor.id,
                    "identifier": sensor.identifier,
                    "name": sensor.name,
                    "status": sensor.status,
                    "source": "external_sql",
                    "readings": sampled,
                }

    q = (
        select(TelemetryReading)
        .where(TelemetryReading.sensor_id == sensor.id)
        .order_by(TelemetryReading.timestamp.desc())
        .limit(min(limit, 200))
    )
    rows = list((await db.execute(q)).scalars().all())
    rows.reverse()

    return {
        "sensor_id": sensor.id,
        "identifier": sensor.identifier,
        "name": sensor.name,
        "status": sensor.status,
        "source": "local_db",
        "readings": [
            {
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "temperature": r.temperature,
                "humidity": r.humidity,
                "raw_data": r.raw_data or {},
            }
            for r in rows
        ],
    }


@router.get("/virtual/states")
async def get_virtual_states(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get persisted virtual light, switch, lock, and cable layer states from the database."""
    res = await db.execute(
        select(SystemConfig).where(SystemConfig.key == "virtual_device_states")
    )
    cfg = res.scalar_one_or_none()
    if not cfg or not cfg.value:
        return {"states": {}}
    try:
        return {"states": json.loads(cfg.value)}
    except Exception:
        return {"states": {}}


@router.post("/virtual/states")
async def update_virtual_state(
    data: VirtualStateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Persist virtual light/switch/lock/layer state in the database and broadcast via WebSocket."""
    res = await db.execute(
        select(SystemConfig).where(SystemConfig.key == "virtual_device_states")
    )
    cfg = res.scalar_one_or_none()
    states: Dict[str, Any] = {}
    if cfg and cfg.value:
        try:
            states = json.loads(cfg.value)
        except Exception:
            states = {}

    states[data.entity_id] = {
        "state": data.state,
        "attributes": data.attributes,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if not cfg:
        cfg = SystemConfig(key="virtual_device_states", value=json.dumps(states))
        db.add(cfg)
    else:
        cfg.value = json.dumps(states)

    await db.commit()

    await notifier.broadcast_json(
        {
            "type": "virtual_state",
            "entity_id": data.entity_id,
            "state": data.state,
            "attributes": data.attributes,
        }
    )

    return {"status": "ok", "entity_id": data.entity_id, "state": data.state}


@router.delete("/virtual/states/{entity_id:path}")
async def delete_virtual_state(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Remove a virtual light/switch state from persisted SystemConfig."""
    res = await db.execute(
        select(SystemConfig).where(SystemConfig.key == "virtual_device_states")
    )
    cfg = res.scalar_one_or_none()
    if cfg and cfg.value:
        try:
            states = json.loads(cfg.value)
            if entity_id in states:
                del states[entity_id]
                cfg.value = json.dumps(states)
                await db.commit()
        except Exception:
            pass
    return {"status": "deleted", "entity_id": entity_id}

