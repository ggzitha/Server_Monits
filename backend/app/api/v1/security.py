"""
security.py - Phase 6 Security Devices API:
- CCTV cameras (live stream/snapshot/wall + 3D FOV cones)
- Door access & biometric fingerprint readers (lock/unlock, grant/deny access logs)
- Motion & door/rack contact sensors (arm/disarm, alert trigger/ack)
- Single source of truth synced with `active_3d_building` (2D & 3D), RBAC, AuditLog & WebSocket.
"""
import html
import json
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_db, require_permission
from backend.app.core.security import decrypt_secret
from backend.app.db.models.audit import AuditLog
from backend.app.db.models.security import SecurityDevice, SecurityEvent
from backend.app.db.models.system_config import SystemConfig
from backend.app.db.models.user import User
from backend.app.services.notifier import notifier

router = APIRouter(prefix="/security", tags=["security"])

VALID_KINDS = {"cctv", "door_access", "fingerprint", "motion", "contact"}
DEFAULT_STATE_BY_KIND = {
    "cctv": "recording",
    "door_access": "locked",
    "fingerprint": "locked",
    "motion": "clear",
    "contact": "closed",
}
ENTITY_PREFIX_BY_KIND = {
    "cctv": "camera",
    "door_access": "lock",
    "fingerprint": "lock",
    "motion": "binary_sensor",
    "contact": "binary_sensor",
}

DEFAULT_SECURITY_DEVICES: List[Dict[str, Any]] = [
    {
        "entity_id": "camera.server_alpha_cam",
        "name": "CCTV Server Alpha Aisle",
        "device_kind": "cctv",
        "floor_id": "ground",
        "room_id": "room_server_a",
        "pos_x": 9.2,
        "pos_z": 0.8,
        "pos_y": 3.1,
        "rotation": 225.0,
        "fov_deg": 75.0,
        "reach_m": 7.0,
        "cone_enabled": True,
        "state": "recording",
    },
    {
        "entity_id": "camera.noc_entry_cam",
        "name": "CCTV NOC Entry Hall",
        "device_kind": "cctv",
        "floor_id": "ground",
        "room_id": "room_noc",
        "pos_x": 11.4,
        "pos_z": 6.2,
        "pos_y": 3.0,
        "rotation": 315.0,
        "fov_deg": 80.0,
        "reach_m": 6.5,
        "cone_enabled": True,
        "state": "recording",
    },
    {
        "entity_id": "lock.server_alpha_door",
        "name": "Server Alpha Biometric Door",
        "device_kind": "fingerprint",
        "floor_id": "ground",
        "room_id": "room_server_a",
        "pos_x": 6.0,
        "pos_z": 6.0,
        "pos_y": 1.35,
        "rotation": 0.0,
        "fov_deg": 0.0,
        "reach_m": 0.0,
        "cone_enabled": False,
        "state": "locked",
    },
    {
        "entity_id": "binary_sensor.server_alpha_motion",
        "name": "Cold Aisle Motion Sensor",
        "device_kind": "motion",
        "floor_id": "ground",
        "room_id": "room_server_a",
        "pos_x": 4.8,
        "pos_z": 1.4,
        "pos_y": 2.6,
        "rotation": 180.0,
        "fov_deg": 90.0,
        "reach_m": 5.0,
        "cone_enabled": True,
        "state": "clear",
    },
    {
        "entity_id": "binary_sensor.server_alpha_door",
        "name": "Server Alpha Door Contact",
        "device_kind": "contact",
        "floor_id": "ground",
        "room_id": "room_server_a",
        "pos_x": 6.1,
        "pos_z": 6.0,
        "pos_y": 2.1,
        "rotation": 0.0,
        "fov_deg": 0.0,
        "reach_m": 0.0,
        "cone_enabled": False,
        "state": "closed",
    },
]


class SecurityDeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=140)
    device_kind: str = Field(default="cctv", max_length=32)
    entity_id: Optional[str] = Field(default=None, max_length=120)
    floor_id: str = Field(default="ground", max_length=64)
    room_id: Optional[str] = Field(default=None, max_length=100)
    pos_x: float = 3.0
    pos_z: float = 2.0
    pos_y: float = 2.8
    rotation: float = 180.0
    fov_deg: float = Field(default=75.0, ge=0.0, le=180.0)
    reach_m: float = Field(default=7.0, ge=0.0, le=50.0)
    cone_enabled: bool = True
    stream_url: str = Field(default="", max_length=500)
    snapshot_url: str = Field(default="", max_length=500)
    armed: bool = True
    notes: Optional[str] = None
    sync_floor_plan: bool = True


class SecurityDeviceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=140)
    floor_id: Optional[str] = Field(default=None, max_length=64)
    room_id: Optional[str] = Field(default=None, max_length=100)
    pos_x: Optional[float] = None
    pos_z: Optional[float] = None
    pos_y: Optional[float] = None
    rotation: Optional[float] = None
    fov_deg: Optional[float] = Field(default=None, ge=0.0, le=180.0)
    reach_m: Optional[float] = Field(default=None, ge=0.0, le=50.0)
    cone_enabled: Optional[bool] = None
    stream_url: Optional[str] = Field(default=None, max_length=500)
    snapshot_url: Optional[str] = Field(default=None, max_length=500)
    state: Optional[str] = Field(default=None, max_length=32)
    armed: Optional[bool] = None
    notes: Optional[str] = None


class SecurityActionPayload(BaseModel):
    action: str = Field(min_length=1, max_length=48)
    actor: Optional[str] = Field(default=None, max_length=120)
    message: Optional[str] = Field(default=None, max_length=255)


def _slugify(val: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (val or "").strip().lower()).strip("_")
    return s or uuid.uuid4().hex[:8]


def _serialize_device(d: SecurityDevice) -> Dict[str, Any]:
    return {
        "id": d.id,
        "entity_id": d.entity_id,
        "name": d.name,
        "device_kind": d.device_kind,
        "floor_id": d.floor_id,
        "room_id": d.room_id,
        "pos_x": round(float(d.pos_x), 3),
        "pos_z": round(float(d.pos_z), 3),
        "pos_y": round(float(d.pos_y), 3),
        "rotation": round(float(d.rotation), 1),
        "fov_deg": round(float(d.fov_deg), 1),
        "reach_m": round(float(d.reach_m), 2),
        "cone_enabled": bool(d.cone_enabled),
        "stream_url": d.stream_url or "",
        "snapshot_url": d.snapshot_url or "",
        "snapshot_endpoint": f"/api/v1/security/cameras/{d.id}/snapshot" if d.device_kind == "cctv" else "",
        "stream_endpoint": f"/api/v1/security/cameras/{d.id}/stream" if d.device_kind == "cctv" else "",
        "state": d.state,
        "armed": bool(d.armed),
        "alert_active": bool(d.alert_active),
        "alert_message": d.alert_message or "",
        "last_event_at": d.last_event_at.isoformat() if d.last_event_at else None,
        "notes": d.notes or "",
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


def _serialize_event(ev: SecurityEvent, dev_map: Dict[str, SecurityDevice]) -> Dict[str, Any]:
    dev = dev_map.get(ev.device_id)
    return {
        "id": ev.id,
        "device_id": ev.device_id,
        "device_name": dev.name if dev else ev.device_id,
        "device_kind": dev.device_kind if dev else "",
        "entity_id": dev.entity_id if dev else "",
        "event_type": ev.event_type,
        "severity": ev.severity,
        "actor": ev.actor,
        "message": ev.message,
        "acknowledged": bool(ev.acknowledged),
        "acknowledged_by": ev.acknowledged_by,
        "acknowledged_at": ev.acknowledged_at.isoformat() if ev.acknowledged_at else None,
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
    }


async def _write_audit(
    db: AsyncSession,
    user: User,
    request: Request,
    action: str,
    resource_id: Optional[str],
    details: Dict[str, Any],
) -> None:
    db.add(
        AuditLog(
            user_id=user.id,
            action=action,
            resource_type="security_device",
            resource_id=resource_id,
            ip_address=request.client.host if request.client else "127.0.0.1",
            user_agent=request.headers.get("user-agent", "")[:255],
            details=details,
        )
    )


async def _upsert_security_device_in_building(
    db: AsyncSession,
    dev: SecurityDevice,
    remove: bool = False,
) -> None:
    """Keep `active_3d_building` placements & fingerprint furniture synchronized with DB security_devices."""
    cfg_res = await db.execute(select(SystemConfig).where(SystemConfig.key == "active_3d_building"))
    cfg = cfg_res.scalar_one_or_none()
    if not cfg or not cfg.value:
        return
    try:
        payload = json.loads(cfg.value)
        is_wrapped = isinstance(payload, dict) and "building" in payload
        building = payload["building"] if is_wrapped else payload
        floors = building.get("floors", []) if isinstance(building, dict) else []
    except Exception:
        return
    if not floors:
        return

    furn_id = f"sec_unit_{dev.id[:8]}"
    for fl in floors:
        if isinstance(fl.get("placements"), list):
            fl["placements"] = [p for p in fl["placements"] if str(p.get("entity_id")) != dev.entity_id]
        if isinstance(fl.get("furniture"), list):
            fl["furniture"] = [f for f in fl["furniture"] if str(f.get("id")) != furn_id]

    if not remove:
        target_fl = next((fl for fl in floors if fl.get("id") == dev.floor_id), floors[0])
        plc: Dict[str, Any] = {
            "entity_id": dev.entity_id,
            "x": round(float(dev.pos_x), 2),
            "z": round(float(dev.pos_z), 2),
            "y": round(float(dev.pos_y), 2),
            "rotation": round(float(dev.rotation), 1),
            "name": dev.name,
            "show_name": True,
            "marker": "always",
        }
        if dev.device_kind in ("cctv", "motion"):
            plc["fov"] = round(float(dev.fov_deg), 1)
            plc["reach"] = round(float(dev.reach_m), 2)
            plc["cone"] = bool(dev.cone_enabled)
        target_fl.setdefault("placements", []).append(plc)

        if dev.device_kind in ("fingerprint", "door_access"):
            target_fl.setdefault("furniture", []).append(
                {
                    "id": furn_id,
                    "type": "pack:dcim.facility:fingerprint_reader",
                    "name": dev.name,
                    "show_name": True,
                    "x": round(float(dev.pos_x), 2),
                    "z": round(float(dev.pos_z), 2),
                    "w": 0.14,
                    "d": 0.05,
                    "h": 0.20,
                    "mount_y": round(float(dev.pos_y), 2),
                    "rotation": round(float(dev.rotation), 1),
                    "entity": dev.entity_id,
                }
            )

    cfg.value = json.dumps(payload)


async def _ensure_default_security_devices(db: AsyncSession) -> List[SecurityDevice]:
    existing = (await db.execute(select(SecurityDevice).order_by(SecurityDevice.device_kind, SecurityDevice.name))).scalars().all()
    if existing:
        return list(existing)

    created: List[SecurityDevice] = []
    for spec in DEFAULT_SECURITY_DEVICES:
        dev = SecurityDevice(**spec)
        db.add(dev)
        created.append(dev)
    await db.flush()
    await db.commit()
    return created


def render_offline_cctv_svg(dev: SecurityDevice) -> str:
    """Generate a live, crisp 100% air-gapped CCTV HUD frame SVG (with REC/ALERT telemetry & UTC clock)."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    safe_name = html.escape(dev.name)
    safe_ent = html.escape(dev.entity_id)
    is_alert = bool(dev.alert_active)
    is_rec = dev.state == "recording"
    accent = "#ef4444" if is_alert else ("#22c55e" if is_rec else "#38bdf8")
    badge_txt = "● ALERT" if is_alert else ("● REC" if is_rec else f"● {dev.state.upper()}")
    alert_bar = (
        f'<rect x="16" y="294" width="608" height="44" rx="6" fill="rgba(239,68,68,0.88)"/>'
        f'<text x="320" y="321" text-anchor="middle" fill="#ffffff" font-size="14" font-weight="700">'
        f'⚠ {html.escape(dev.alert_message or "SECURITY ALERT ACTIVE")}</text>'
        if is_alert
        else ""
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360" '
        'style="font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;">'
        '<defs>'
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0%" stop-color="#050b16"/>'
        '<stop offset="100%" stop-color="#0f1d33"/>'
        '</linearGradient>'
        '<pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">'
        '<path d="M 32 0 L 0 0 0 32" fill="none" stroke="rgba(56,189,248,0.08)" stroke-width="1"/>'
        '</pattern>'
        '</defs>'
        '<rect width="640" height="360" fill="url(#bg)"/>'
        '<rect width="640" height="360" fill="url(#grid)"/>'
        # Perspective data center aisle wireframe
        '<polygon points="150,360 250,150 390,150 490,360" fill="rgba(0,240,255,0.04)" stroke="rgba(0,240,255,0.22)" stroke-width="1.2"/>'
        '<rect x="64" y="100" width="90" height="210" rx="4" fill="rgba(15,23,42,0.8)" stroke="rgba(56,189,248,0.35)"/>'
        '<rect x="486" y="100" width="90" height="210" rx="4" fill="rgba(15,23,42,0.8)" stroke="rgba(56,189,248,0.35)"/>'
        # Crosshair reticle
        '<circle cx="320" cy="180" r="38" fill="none" stroke="rgba(56,189,248,0.28)" stroke-dasharray="4 4"/>'
        '<line x1="296" y1="180" x2="344" y2="180" stroke="rgba(56,189,248,0.35)"/>'
        '<line x1="320" y1="156" x2="320" y2="204" stroke="rgba(56,189,248,0.35)"/>'
        # Top HUD bar
        '<rect x="14" y="14" width="612" height="34" rx="6" fill="rgba(5,10,22,0.78)" stroke="rgba(148,163,184,0.25)"/>'
        f'<text x="26" y="36" fill="#e2e8f0" font-size="13" font-weight="700">📹 {safe_name}</text>'
        f'<rect x="524" y="21" width="92" height="20" rx="10" fill="{accent}"/>'
        f'<text x="570" y="35" text-anchor="middle" fill="#ffffff" font-size="11" font-weight="700">{badge_txt}</text>'
        # Bottom HUD telemetry
        '<rect x="14" y="316" width="612" height="30" rx="6" fill="rgba(5,10,22,0.72)"/>'
        f'<text x="24" y="335" fill="#94a3b8" font-size="11">{safe_ent} · FOV {dev.fov_deg:.0f}° · Reach {dev.reach_m:.1f}m · Floor: {html.escape(dev.floor_id)}</text>'
        f'<text x="614" y="335" text-anchor="end" fill="#38bdf8" font-size="11">{ts}</text>'
        f'{alert_bar}'
        '</svg>'
    )


@router.get("/devices")
async def list_security_devices(
    device_kind: Optional[str] = Query(default=None),
    floor_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("security:read")),
):
    devices = await _ensure_default_security_devices(db)
    if device_kind:
        devices = [d for d in devices if d.device_kind == device_kind]
    if floor_id:
        devices = [d for d in devices if d.floor_id == floor_id]
    active_alerts = sum(1 for d in devices if d.alert_active)
    return {
        "devices": [_serialize_device(d) for d in devices],
        "count": len(devices),
        "active_alerts": active_alerts,
    }


@router.post("/devices", status_code=status.HTTP_201_CREATED)
async def create_security_device(
    body: SecurityDeviceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("security:write")),
):
    if body.device_kind not in VALID_KINDS:
        raise HTTPException(status_code=400, detail=f"Invalid device_kind '{body.device_kind}'")

    prefix = ENTITY_PREFIX_BY_KIND[body.device_kind]
    ent = (body.entity_id or "").strip()
    if not ent:
        ent = f"{prefix}.{_slugify(body.name)}_{uuid.uuid4().hex[:4]}"
    elif "." not in ent:
        ent = f"{prefix}.{_slugify(ent)}"

    exists = (await db.execute(select(SecurityDevice).where(SecurityDevice.entity_id == ent))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail=f"Entity '{ent}' already exists")

    dev = SecurityDevice(
        entity_id=ent,
        name=body.name.strip(),
        device_kind=body.device_kind,
        floor_id=body.floor_id,
        room_id=body.room_id,
        pos_x=body.pos_x,
        pos_z=body.pos_z,
        pos_y=body.pos_y,
        rotation=body.rotation,
        fov_deg=body.fov_deg if body.device_kind in ("cctv", "motion") else 0.0,
        reach_m=body.reach_m if body.device_kind in ("cctv", "motion") else 0.0,
        cone_enabled=body.cone_enabled if body.device_kind in ("cctv", "motion") else False,
        stream_url=body.stream_url.strip(),
        snapshot_url=body.snapshot_url.strip(),
        state=DEFAULT_STATE_BY_KIND[body.device_kind],
        armed=body.armed,
        notes=body.notes,
    )
    db.add(dev)
    await db.flush()
    if body.sync_floor_plan:
        await _upsert_security_device_in_building(db, dev, remove=False)
    await _write_audit(db, current_user, request, "security.device.create", dev.id, {"name": dev.name, "kind": dev.device_kind})
    await db.commit()
    await notifier.broadcast_json({"type": "security_updated", "action": "create", "device_id": dev.id})
    return _serialize_device(dev)


@router.patch("/devices/{device_id}")
async def update_security_device(
    device_id: str,
    body: SecurityDeviceUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("security:write")),
):
    dev = (await db.execute(select(SecurityDevice).where(SecurityDevice.id == device_id))).scalar_one_or_none()
    if not dev:
        raise HTTPException(status_code=404, detail="Security device not found")
    for fld in ("name", "floor_id", "room_id", "pos_x", "pos_z", "pos_y", "rotation", "fov_deg", "reach_m", "cone_enabled", "stream_url", "snapshot_url", "state", "armed", "notes"):
        val = getattr(body, fld)
        if val is not None:
            setattr(dev, fld, val.strip() if isinstance(val, str) else val)
    await _upsert_security_device_in_building(db, dev, remove=False)
    await _write_audit(db, current_user, request, "security.device.update", dev.id, {"name": dev.name})
    await db.commit()
    await notifier.broadcast_json({"type": "security_updated", "action": "update", "device_id": dev.id})
    return _serialize_device(dev)


@router.delete("/devices/{device_id}")
async def delete_security_device(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("security:write")),
):
    dev = (await db.execute(select(SecurityDevice).where(SecurityDevice.id == device_id))).scalar_one_or_none()
    if not dev:
        raise HTTPException(status_code=404, detail="Security device not found")
    name = dev.name
    await _upsert_security_device_in_building(db, dev, remove=True)
    await db.delete(dev)
    await _write_audit(db, current_user, request, "security.device.delete", device_id, {"name": name})
    await db.commit()
    await notifier.broadcast_json({"type": "security_updated", "action": "delete", "device_id": device_id})
    return {"deleted": True, "id": device_id}


@router.post("/devices/{device_id}/action")
async def execute_security_action(
    device_id: str,
    body: SecurityActionPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("security:write")),
):
    """Execute live security controls (lock/unlock, grant/deny badge, motion/contact trigger, cone toggle, alert ack)."""
    dev = (await db.execute(select(SecurityDevice).where(SecurityDevice.id == device_id))).scalar_one_or_none()
    if not dev:
        raise HTTPException(status_code=404, detail="Security device not found")

    act = body.action.strip().lower()
    actor = (body.actor or current_user.username or "operator").strip()
    now = datetime.now(timezone.utc)
    ev_type = act
    severity = "info"
    msg = body.message or ""

    if act == "lock":
        dev.state = "locked"
        dev.alert_active = False
        dev.alert_message = ""
        ev_type = "lock_toggled"
        msg = msg or f"Locked {dev.name}"
    elif act == "unlock":
        dev.state = "unlocked"
        ev_type = "lock_toggled"
        msg = msg or f"Unlocked {dev.name}"
    elif act == "grant_access":
        dev.state = "unlocked"
        dev.alert_active = False
        dev.alert_message = ""
        ev_type = "access_granted"
        msg = msg or f"Biometric/badge access granted for {actor}"
    elif act == "deny_access":
        dev.state = "locked"
        dev.alert_active = True
        dev.alert_message = msg or f"Unauthorized access attempt at {dev.name} ({actor})"
        ev_type = "access_denied"
        severity = "critical"
        msg = dev.alert_message
    elif act == "trigger_motion":
        dev.state = "detected"
        dev.alert_active = bool(dev.armed)
        dev.alert_message = msg or f"Motion detected by {dev.name}"
        ev_type = "motion_detected"
        severity = "warning" if dev.armed else "info"
        msg = dev.alert_message
    elif act == "clear_motion":
        dev.state = "clear"
        dev.alert_active = False
        dev.alert_message = ""
        ev_type = "motion_cleared"
        msg = msg or f"Motion cleared on {dev.name}"
    elif act == "open_door":
        dev.state = "open"
        dev.alert_active = bool(dev.armed)
        dev.alert_message = msg or f"Door opened while armed: {dev.name}"
        ev_type = "door_forced" if dev.armed else "door_opened"
        severity = "critical" if dev.armed else "info"
        msg = dev.alert_message
    elif act == "close_door":
        dev.state = "closed"
        dev.alert_active = False
        dev.alert_message = ""
        ev_type = "door_closed"
        msg = msg or f"Door closed: {dev.name}"
    elif act == "trigger_alert":
        dev.alert_active = True
        dev.alert_message = msg or f"Camera/Security alert on {dev.name}"
        ev_type = "camera_alert"
        severity = "critical"
        msg = dev.alert_message
    elif act == "ack_alert":
        dev.alert_active = False
        dev.alert_message = ""
        ev_type = "alert_ack"
        msg = msg or f"Alert acknowledged by {actor}"
        # Also mark unacknowledged events on this device as acknowledged
        unacked = (await db.execute(
            select(SecurityEvent).where(SecurityEvent.device_id == dev.id, SecurityEvent.acknowledged.is_(False))
        )).scalars().all()
        for uev in unacked:
            uev.acknowledged = True
            uev.acknowledged_by = actor
            uev.acknowledged_at = now
    elif act == "toggle_recording":
        dev.state = "idle" if dev.state == "recording" else "recording"
        ev_type = "camera_mode"
        msg = msg or f"Camera state set to {dev.state}"
    elif act == "toggle_cone":
        dev.cone_enabled = not bool(dev.cone_enabled)
        await _upsert_security_device_in_building(db, dev, remove=False)
        ev_type = "cone_toggled"
        msg = msg or f"3D FOV cone {'enabled' if dev.cone_enabled else 'disabled'}"
    elif act == "toggle_arm":
        dev.armed = not bool(dev.armed)
        ev_type = "arm_toggled"
        msg = msg or f"Sensor {'armed' if dev.armed else 'disarmed'}"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action '{act}'")

    dev.last_event_at = now
    ev = SecurityEvent(
        device_id=dev.id,
        event_type=ev_type,
        severity=severity,
        actor=actor,
        message=msg,
        acknowledged=(severity == "info" or act == "ack_alert"),
        acknowledged_by=actor if act == "ack_alert" else None,
        acknowledged_at=now if act == "ack_alert" else None,
    )
    db.add(ev)
    await db.flush()
    await _write_audit(db, current_user, request, f"security.action.{act}", dev.id, {"entity_id": dev.entity_id, "state": dev.state, "alert": dev.alert_active})
    await db.commit()

    await notifier.broadcast_json({
        "type": "security_event",
        "device": _serialize_device(dev),
        "event": _serialize_event(ev, {dev.id: dev}),
    })
    return {
        "device": _serialize_device(dev),
        "event": _serialize_event(ev, {dev.id: dev}),
    }


@router.get("/events")
async def list_security_events(
    device_id: Optional[str] = Query(default=None),
    unacknowledged_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("security:read")),
):
    stmt = select(SecurityEvent).order_by(SecurityEvent.created_at.desc()).limit(limit)
    if device_id:
        stmt = stmt.where(SecurityEvent.device_id == device_id)
    if unacknowledged_only:
        stmt = stmt.where(SecurityEvent.acknowledged.is_(False))
    events = (await db.execute(stmt)).scalars().all()
    devs = (await db.execute(select(SecurityDevice))).scalars().all()
    dev_map = {d.id: d for d in devs}
    return {
        "events": [_serialize_event(e, dev_map) for e in events],
        "count": len(events),
    }


@router.post("/events/{event_id}/ack")
async def acknowledge_security_event(
    event_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("security:write")),
):
    ev = (await db.execute(select(SecurityEvent).where(SecurityEvent.id == event_id))).scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Security event not found")
    ev.acknowledged = True
    ev.acknowledged_by = current_user.username
    ev.acknowledged_at = datetime.now(timezone.utc)
    # Clear device alert if no remaining unacknowledged warning/critical events
    remaining = (await db.execute(
        select(SecurityEvent).where(
            SecurityEvent.device_id == ev.device_id,
            SecurityEvent.acknowledged.is_(False),
            SecurityEvent.severity.in_(("warning", "critical")),
            SecurityEvent.id != ev.id,
        )
    )).scalars().first()
    if not remaining:
        dev = (await db.execute(select(SecurityDevice).where(SecurityDevice.id == ev.device_id))).scalar_one_or_none()
        if dev:
            dev.alert_active = False
            dev.alert_message = ""
    await _write_audit(db, current_user, request, "security.event.ack", ev.id, {"device_id": ev.device_id})
    await db.commit()
    return {"acknowledged": True, "id": ev.id}


def resolve_frigate_go2rtc_urls(stream_url: str, snapshot_url: str = "") -> Dict[str, List[str]]:
    """
    Resolve Frigate / go2rtc / direct HTTP / RTSP camera URLs into ordered candidate lists
    for live JPEG snapshots and live MJPEG streams.

    Example:
      https://inskal-cctv.balai5.my.id/api/go2rtc/streams/inskal_main_lobby
      -> snapshot_candidates:
         - https://inskal-cctv.balai5.my.id/api/go2rtc/frame.jpeg?src=inskal_main_lobby
         - https://inskal-cctv.balai5.my.id/api/inskal_main_lobby/latest.jpg
      -> stream_candidates:
         - https://inskal-cctv.balai5.my.id/api/go2rtc/stream.mjpeg?src=inskal_main_lobby
         - https://inskal-cctv.balai5.my.id/api/inskal_main_lobby
    """
    raw_stream = (stream_url or "").strip()
    raw_snap = (snapshot_url or "").strip()
    snap_cands: List[str] = []
    stream_cands: List[str] = []
    rtsp_cands: List[str] = []

    def _add_unique(lst: List[str], u: str) -> None:
        if u and u not in lst:
            lst.append(u)

    for candidate in (raw_snap, raw_stream):
        if not candidate:
            continue
        low = candidate.lower()
        if low.startswith("rtsp://") or low.startswith("rtsps://"):
            _add_unique(rtsp_cands, candidate)
            continue
        if not (low.startswith("http://") or low.startswith("https://")):
            continue

        # Detect Frigate go2rtc metadata endpoint: .../api/go2rtc/streams/<name>
        m = re.match(r"^(https?://[^/]+)(?:/api/go2rtc/streams/|/api/streams\?src=)([^/?#&]+)", candidate, re.IGNORECASE)
        if m:
            origin, cam_name = m.group(1), m.group(2)
            enc = quote(cam_name, safe="")
            _add_unique(snap_cands, f"{origin}/api/go2rtc/frame.jpeg?src={enc}")
            _add_unique(snap_cands, f"{origin}/api/{enc}/latest.jpg")
            _add_unique(stream_cands, f"{origin}/api/go2rtc/stream.mjpeg?src={enc}")
            _add_unique(stream_cands, f"{origin}/api/{enc}")
            continue

        # Detect Frigate camera base URL: .../api/<name>/latest.jpg or .../api/go2rtc/frame.jpeg?src=<name>
        if any(k in low for k in (".jpg", ".jpeg", ".png", "frame.jpeg", "latest.jpg", "snapshot")):
            _add_unique(snap_cands, candidate)
        elif any(k in low for k in ("mjpeg", "mjpg", "stream.mp4", "stream")):
            _add_unique(stream_cands, candidate)
        else:
            # Generic HTTP URL — try as both snapshot and stream
            if candidate == raw_snap:
                _add_unique(snap_cands, candidate)
            else:
                _add_unique(stream_cands, candidate)
                _add_unique(snap_cands, candidate)

    return {
        "snapshot_candidates": snap_cands,
        "stream_candidates": stream_cands,
        "rtsp_candidates": rtsp_cands,
    }


_FRIGATE_COOKIE_CACHE: Dict[str, Tuple[float, Dict[str, str]]] = {}


async def _load_go2rtc_credentials(db: AsyncSession) -> Tuple[str, str, str]:
    """Load saved Frigate/go2rtc username, decrypted password, and optional Bearer token."""
    rows = (await db.execute(
        select(SystemConfig).where(SystemConfig.key.in_(("go2rtc_username", "go2rtc_password", "go2rtc_token")))
    )).scalars().all()
    m = {r.key: r.value for r in rows}
    user = (m.get("go2rtc_username") or "").strip()
    pw = ""
    if m.get("go2rtc_password"):
        try:
            pw = decrypt_secret(m["go2rtc_password"])
        except Exception:
            pw = ""
    tok = ""
    if m.get("go2rtc_token"):
        try:
            tok = decrypt_secret(m["go2rtc_token"]).strip()
        except Exception:
            tok = ""
    return user, pw, tok


async def _get_frigate_cookies(origin: str, username: str, password: str) -> Dict[str, str]:
    """Authenticate against Frigate 0.14+ JWT login (/api/login) and cache the `frigate_token` cookie for 10 min."""
    if not origin or not username or not password:
        return {}
    now_ts = datetime.now(timezone.utc).timestamp()
    cache_key = f"{origin}|{username}"
    cached = _FRIGATE_COOKIE_CACHE.get(cache_key)
    if cached and cached[0] > now_ts:
        return dict(cached[1])
    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False, follow_redirects=True) as c:
            r = await c.post(f"{origin}/api/login", json={"user": username, "password": password})
            if r.status_code == 200 and c.cookies:
                jar = {k: v for k, v in c.cookies.items()}
                _FRIGATE_COOKIE_CACHE[cache_key] = (now_ts + 600.0, jar)
                return dict(jar)
    except Exception:
        pass
    return {}


@router.get("/cameras/{device_id}/snapshot")
async def get_camera_snapshot(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("cameras:view")),
):
    """
    Return live CCTV snapshot:
    1. If a Frigate / go2rtc / HTTP snapshot URL is configured, authenticate via Frigate JWT cookie or Basic Auth and proxy JPEG/PNG server-side.
    2. If an RTSP URL is configured and `ffmpeg` is installed, grab a single JPEG frame.
    3. Otherwise return the crisp offline SVG HUD frame.
    """
    dev = (await db.execute(select(SecurityDevice).where(SecurityDevice.id == device_id))).scalar_one_or_none()
    if not dev:
        raise HTTPException(status_code=404, detail="Camera not found")

    resolved = resolve_frigate_go2rtc_urls(dev.stream_url, dev.snapshot_url)
    user, pw, tok = await _load_go2rtc_credentials(db)
    headers = {"Authorization": f"Bearer {tok}"} if tok else {}

    # 1. Try Frigate / go2rtc / HTTP snapshot candidates via server-side httpx
    if resolved["snapshot_candidates"]:
        first_p = urlparse(resolved["snapshot_candidates"][0])
        origin = f"{first_p.scheme}://{first_p.netloc}" if first_p.scheme and first_p.netloc else ""
        cookies = await _get_frigate_cookies(origin, user, pw)
        auth = None if cookies else (httpx.BasicAuth(user, pw) if (user or pw) else None)
        async with httpx.AsyncClient(timeout=4.5, verify=False, follow_redirects=True, auth=auth, headers=headers, cookies=cookies) as client_http:
            for url in resolved["snapshot_candidates"]:
                try:
                    resp = await client_http.get(url)
                    ct = (resp.headers.get("content-type") or "").lower()
                    if resp.status_code == 200 and ct.startswith("image/") and len(resp.content) > 256:
                        return Response(
                            content=resp.content,
                            media_type=ct.split(";")[0],
                            headers={"Cache-Control": "no-store, max-age=0"},
                        )
                except Exception:
                    continue

    # 2. Try ffmpeg single-frame grab for rtsp:// if ffmpeg is available on host
    ffmpeg_bin = shutil.which("ffmpeg")
    if resolved["rtsp_candidates"] and ffmpeg_bin:
        for rtsp_url in resolved["rtsp_candidates"]:
            try:
                proc = subprocess.run(
                    [
                        ffmpeg_bin, "-hide_banner", "-loglevel", "error",
                        "-rtsp_transport", "tcp", "-i", rtsp_url,
                        "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-",
                    ],
                    capture_output=True,
                    timeout=5,
                )
                if proc.returncode == 0 and len(proc.stdout) > 256:
                    return Response(
                        content=proc.stdout,
                        media_type="image/jpeg",
                        headers={"Cache-Control": "no-store, max-age=0"},
                    )
            except Exception:
                continue

    # 3. Fallback: crisp offline SVG HUD frame
    svg = render_offline_cctv_svg(dev)
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.get("/cameras/{device_id}/stream")
async def get_camera_stream(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("cameras:view")),
):
    """Proxy live MJPEG stream from Frigate / go2rtc (or fall back to snapshot if unavailable)."""
    dev = (await db.execute(select(SecurityDevice).where(SecurityDevice.id == device_id))).scalar_one_or_none()
    if not dev:
        raise HTTPException(status_code=404, detail="Camera not found")

    resolved = resolve_frigate_go2rtc_urls(dev.stream_url, dev.snapshot_url)
    user, pw, tok = await _load_go2rtc_credentials(db)
    headers = {"Authorization": f"Bearer {tok}"} if tok else {}
    first_p = urlparse(resolved["stream_candidates"][0]) if resolved["stream_candidates"] else None
    origin = f"{first_p.scheme}://{first_p.netloc}" if first_p and first_p.scheme and first_p.netloc else ""
    cookies = await _get_frigate_cookies(origin, user, pw)
    auth = None if cookies else (httpx.BasicAuth(user, pw) if (user or pw) else None)
    for url in resolved["stream_candidates"]:
        try:
            client_http = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0),
                verify=False,
                follow_redirects=True,
                auth=auth,
                headers=headers,
                cookies=cookies,
            )
            req = client_http.build_request("GET", url)
            resp = await client_http.send(req, stream=True)
            ct = resp.headers.get("content-type") or "multipart/x-mixed-replace; boundary=frame"
            if resp.status_code == 200 and ("multipart" in ct.lower() or "image/" in ct.lower() or "video/" in ct.lower()):
                async def _iter() -> AsyncIterator[bytes]:
                    try:
                        async for chunk in resp.aiter_bytes(chunk_size=16384):
                            yield chunk
                    finally:
                        await resp.aclose()
                        await client_http.aclose()

                return StreamingResponse(
                    _iter(),
                    media_type=ct,
                    headers={"Cache-Control": "no-store, max-age=0"},
                )
            await resp.aclose()
            await client_http.aclose()
        except Exception:
            continue

    # Fallback to snapshot if live stream not configured/reachable
    return await get_camera_snapshot(device_id, db=db, current_user=current_user)
