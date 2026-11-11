"""
sensors.py - Database-Backed Sensor Telemetry & Virtual Device Control API
Provides direct DB sensor readings, historical sparkline time-series, and virtual light/switch persistence
completely detached from Home Assistant.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user, get_db
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
    area_id: Optional[str] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    power_kw: Optional[float] = None
    wifi_dbm: Optional[float] = None
    battery_level: Optional[float] = None


class VirtualStateUpdate(BaseModel):
    entity_id: str = Field(..., min_length=1, max_length=150)
    state: str = Field(..., min_length=1, max_length=50)
    attributes: Dict[str, Any] = Field(default_factory=dict)


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
                "current_temperature": s.current_temperature,
                "current_humidity": s.current_humidity,
                "power_kw": meta.get("power_kw"),
                "wifi_dbm": meta.get("wifi_dbm"),
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


@router.post("/readings", status_code=status.HTTP_200_OK)
async def push_sensor_reading(
    data: DirectReadingInput,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Directly record a sensor reading into the database and broadcast live via WebSocket."""
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

    # Also update metadata (area_id, power_kw, wifi_dbm, custom name) on the Sensor row
    stmt = select(Sensor).where(Sensor.identifier == data.identifier)
    sensor = (await db.execute(stmt)).scalar_one_or_none()
    if sensor:
        if data.name:
            sensor.name = data.name
        meta = dict(sensor.metadata_json or {})
        if data.area_id:
            meta["area_id"] = data.area_id
        if data.power_kw is not None:
            meta["power_kw"] = round(float(data.power_kw), 2)
        if data.wifi_dbm is not None:
            meta["wifi_dbm"] = round(float(data.wifi_dbm), 1)
        sensor.metadata_json = meta
        await db.commit()

        # Force broadcast to all connected 3D views
        await notifier.broadcast_telemetry(
            sensor.identifier,
            {
                "identifier": sensor.identifier,
                "sensor_name": sensor.name,
                "area_id": meta.get("area_id", "server_alpha"),
                "temperature": sensor.current_temperature,
                "humidity": sensor.current_humidity,
                "power_kw": meta.get("power_kw"),
                "wifi_dbm": meta.get("wifi_dbm"),
                "status": sensor.status,
            },
            force=True,
        )

    return {
        **result,
        "power_kw": data.power_kw,
        "wifi_dbm": data.wifi_dbm,
        "area_id": data.area_id,
    }


@router.get("/{identifier}/history")
async def get_sensor_history(
    identifier: str,
    limit: int = 24,
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

