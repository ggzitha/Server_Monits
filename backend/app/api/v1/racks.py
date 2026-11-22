"""
racks.py - Native Rack Management, Interactive Elevation View, Device Library & NetBox Importer API (Phase 5a).

Single source of truth for racks (4U-70U + custom), mounted rack devices with strict U-overlap
and bounds validation, utilization stats, reusable device templates, RBAC enforcement, and AuditLog.
"""
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.deps import get_db, require_permission
from backend.app.db.models.audit import AuditLog
from backend.app.db.models.rack import Rack, RackDevice, RackDeviceTemplate
from backend.app.db.models.system_config import SystemConfig
from backend.app.db.models.user import User
from backend.app.services.notifier import notifier

router = APIRouter(prefix="/racks", tags=["racks"])

VALID_DEVICE_TYPES = {
    "server",
    "switch",
    "patch_panel",
    "pdu",
    "ups",
    "storage",
    "blank_panel",
    "custom",
}
VALID_FACES = {"front", "rear", "both"}
VALID_HALF_SLOTS = {"full", "left", "right"}
VALID_STATUSES = {"active", "planned", "offline", "maintenance", "decommissioned"}

BUILTIN_TEMPLATES: List[Dict[str, Any]] = [
    {"name": "1U Compute Server", "device_type": "server", "manufacturer": "Generic", "model": "1U Dual-Socket Server", "u_height": 1, "is_full_depth": True, "half_width": False, "power_w": 350.0, "color": "#0284c7"},
    {"name": "2U Compute / GPU Server", "device_type": "server", "manufacturer": "Generic", "model": "2U Enterprise Server", "u_height": 2, "is_full_depth": True, "half_width": False, "power_w": 650.0, "color": "#0369a1"},
    {"name": "4U Storage Array (24-Bay)", "device_type": "storage", "manufacturer": "Generic", "model": "4U NVMe/SAS Storage", "u_height": 4, "is_full_depth": True, "half_width": False, "power_w": 850.0, "color": "#7c3aed"},
    {"name": "1U 48-Port ToR Switch", "device_type": "switch", "manufacturer": "Generic", "model": "48x10G + 6x100G Switch", "u_height": 1, "is_full_depth": False, "half_width": False, "power_w": 180.0, "color": "#059669"},
    {"name": "1U 24-Port Patch Panel", "device_type": "patch_panel", "manufacturer": "Generic", "model": "Cat6A / OM4 Patch Panel", "u_height": 1, "is_full_depth": False, "half_width": False, "power_w": 0.0, "color": "#475569"},
    {"name": "1U Metered Rack PDU", "device_type": "pdu", "manufacturer": "Generic", "model": "1U Switched PDU", "u_height": 1, "is_full_depth": False, "half_width": False, "power_w": 15.0, "color": "#d97706"},
    {"name": "2U Online Rack UPS (3kVA)", "device_type": "ups", "manufacturer": "Generic", "model": "3000VA Double-Conversion UPS", "u_height": 2, "is_full_depth": True, "half_width": False, "power_w": 120.0, "color": "#dc2626"},
    {"name": "1U Blanking Panel", "device_type": "blank_panel", "manufacturer": "Generic", "model": "Airflow Blank 1U", "u_height": 1, "is_full_depth": False, "half_width": False, "power_w": 0.0, "color": "#64748b"},
    {"name": "1U Half-Width Firewall", "device_type": "custom", "manufacturer": "Generic", "model": "Compact Security Appliance", "u_height": 1, "is_full_depth": False, "half_width": True, "power_w": 65.0, "color": "#db2777"},
]


# ── Pure validation & utilization helpers (unit-testable) ───────────────────

def faces_conflict(face_a: str, face_b: str) -> bool:
    fa = (face_a or "front").lower()
    fb = (face_b or "front").lower()
    if fa == "both" or fb == "both":
        return True
    return fa == fb


def width_slots_conflict(half_a: bool, slot_a: str, half_b: bool, slot_b: str) -> bool:
    if not half_a or not half_b:
        return True
    sa = (slot_a or "left").lower()
    sb = (slot_b or "left").lower()
    if sa == "full" or sb == "full":
        return True
    return sa == sb


def validate_rack_device_placement(
    rack_u_height: int,
    existing_devices: List[Dict[str, Any]],
    u_position: int,
    u_height: int,
    face: str = "front",
    half_width: bool = False,
    half_slot: str = "full",
    ignore_device_id: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validate a candidate device placement inside a rack of height `rack_u_height` (4..70).
    Returns (True, None) if valid, or (False, error_message) if out-of-range or overlapping.
    """
    if u_height < 1 or u_height > rack_u_height:
        return False, f"Device height ({u_height}U) must be between 1U and {rack_u_height}U."
    top_u = u_position + u_height - 1
    if u_position < 1 or top_u > rack_u_height:
        return False, f"Out of range: U{u_position}-U{top_u} exceeds rack bounds (U1-U{rack_u_height})."

    cand_slot = half_slot if half_width else "full"
    if half_width and cand_slot not in ("left", "right"):
        cand_slot = "left"

    for dev in existing_devices:
        if ignore_device_id and str(dev.get("id")) == str(ignore_device_id):
            continue
        d_pos = int(dev.get("u_position", 1))
        d_h = int(dev.get("u_height", 1))
        d_top = d_pos + d_h - 1
        # Check U interval intersection
        if u_position <= d_top and d_pos <= top_u:
            if faces_conflict(face, dev.get("face", "front")):
                if width_slots_conflict(
                    half_width,
                    cand_slot,
                    bool(dev.get("half_width", False)),
                    dev.get("half_slot", "full"),
                ):
                    return (
                        False,
                        f"Overlap conflict at U{u_position}-U{top_u} with '{dev.get('name', 'Device')}' "
                        f"(U{d_pos}-U{d_top}, {dev.get('face', 'front')}).",
                    )
    return True, None


def compute_rack_utilization(rack_u_height: int, max_power_w: float, devices: List[Dict[str, Any]]) -> Dict[str, Any]:
    occupied_u = set()
    total_power = 0.0
    for d in devices:
        pos = int(d.get("u_position", 1))
        h = int(d.get("u_height", 1))
        for u in range(pos, min(rack_u_height + 1, pos + h)):
            if u >= 1:
                occupied_u.add(u)
        total_power += float(d.get("power_w") or 0.0)
    u_used = len(occupied_u)
    u_free = max(0, rack_u_height - u_used)
    u_pct = round((u_used / max(1, rack_u_height)) * 100.0, 1)
    max_p = max(1.0, float(max_power_w or 5000.0))
    p_pct = round((total_power / max_p) * 100.0, 1)
    return {
        "u_total": rack_u_height,
        "u_used": u_used,
        "u_free": u_free,
        "u_percent": u_pct,
        "total_power_w": round(total_power, 1),
        "max_power_w": round(float(max_power_w or 5000.0), 1),
        "power_percent": p_pct,
        "device_count": len(devices),
    }


def _parse_netbox_device_types(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parse NetBox device-type definitions in JSON or YAML (single doc or multi-doc `---`)
    without requiring PyYAML as a mandatory dependency.
    """
    txt = (raw_text or "").strip()
    if not txt:
        return []

    parsed_docs: List[Any] = []
    # 1. Try JSON first
    try:
        j = json.loads(txt)
        parsed_docs = j if isinstance(j, list) else [j]
    except Exception:
        # 2. Try PyYAML if installed, else lightweight NetBox YAML parser
        try:
            import yaml  # type: ignore
            docs = list(yaml.safe_load_all(txt))
            for d in docs:
                if isinstance(d, list):
                    parsed_docs.extend(d)
                elif isinstance(d, dict):
                    parsed_docs.append(d)
        except Exception:
            for chunk in re.split(r"(?m)^---\s*$", txt):
                chunk = chunk.strip()
                if not chunk:
                    continue
                doc: Dict[str, Any] = {}
                for line in chunk.splitlines():
                    if not line.strip() or line.strip().startswith("#") or line.startswith(" "):
                        continue
                    if ":" in line:
                        k, v = line.split(":", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if v.lower() in ("true", "yes"):
                            doc[k] = True
                        elif v.lower() in ("false", "no"):
                            doc[k] = False
                        else:
                            try:
                                doc[k] = float(v) if "." in v else int(v)
                            except Exception:
                                doc[k] = v
                if doc:
                    parsed_docs.append(doc)

    results: List[Dict[str, Any]] = []
    for item in parsed_docs:
        if not isinstance(item, dict):
            continue
        model = str(item.get("model") or item.get("name") or "").strip()
        if not model:
            continue
        mfr = item.get("manufacturer", "")
        if isinstance(mfr, dict):
            mfr = mfr.get("name", "")
        mfr = str(mfr or "").strip()
        u_h = max(1, min(70, int(round(float(item.get("u_height", 1) or 1)))))
        full_depth = bool(item.get("is_full_depth", True))
        low_model = (model + " " + str(item.get("comments", ""))).lower()
        dtype = str(item.get("device_type") or "").lower()
        if dtype not in VALID_DEVICE_TYPES:
            if "switch" in low_model or "catalyst" in low_model or "nexus" in low_model or "arista" in low_model:
                dtype = "switch"
            elif "ups" in low_model:
                dtype = "ups"
            elif "pdu" in low_model:
                dtype = "pdu"
            elif "patch" in low_model:
                dtype = "patch_panel"
            elif "storage" in low_model or "nas" in low_model or "san" in low_model:
                dtype = "storage"
            elif "blank" in low_model:
                dtype = "blank_panel"
            else:
                dtype = "server"
        power_w = float(item.get("power_w") or item.get("power_draw") or item.get("allocated_draw") or 0.0)
        half_w = bool(item.get("half_width", False))
        results.append({
            "name": f"{mfr} {model}".strip() if mfr else model,
            "device_type": dtype,
            "manufacturer": mfr,
            "model": model,
            "u_height": u_h,
            "is_full_depth": full_depth,
            "half_width": half_w,
            "power_w": power_w,
            "color": str(item.get("color") or "#0284c7"),
            "notes": str(item.get("comments") or item.get("notes") or ""),
        })
    return results


# ── Pydantic Schemas ────────────────────────────────────────────────────────

class RackCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    furniture_id: Optional[str] = None
    floor_id: str = Field(default="ground", max_length=64)
    room_id: Optional[str] = None
    u_height: int = Field(default=42, ge=4, le=70)
    width_in: float = Field(default=19.0, ge=10.0, le=30.0)
    depth_mm: int = Field(default=1000, ge=300, le=1600)
    color: str = Field(default="#1e293b", max_length=32)
    pos_x: float = Field(default=2.0)
    pos_z: float = Field(default=2.0)
    rotation: float = Field(default=0.0)
    max_power_w: float = Field(default=5000.0, ge=100.0, le=100000.0)
    notes: Optional[str] = None
    sync_floor_plan: bool = True


class RackUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    floor_id: Optional[str] = Field(default=None, max_length=64)
    room_id: Optional[str] = None
    u_height: Optional[int] = Field(default=None, ge=4, le=70)
    width_in: Optional[float] = Field(default=None, ge=10.0, le=30.0)
    depth_mm: Optional[int] = Field(default=None, ge=300, le=1600)
    color: Optional[str] = Field(default=None, max_length=32)
    pos_x: Optional[float] = None
    pos_z: Optional[float] = None
    rotation: Optional[float] = None
    max_power_w: Optional[float] = Field(default=None, ge=100.0, le=100000.0)
    notes: Optional[str] = None


class RackDeviceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    device_type: str = Field(default="server", max_length=40)
    manufacturer: str = Field(default="", max_length=80)
    model: str = Field(default="", max_length=120)
    slug: str = Field(default="", max_length=140)
    u_height: int = Field(default=1, ge=1, le=70)
    u_position: int = Field(default=1, ge=1, le=70)
    face: str = Field(default="front", max_length=16)
    is_full_depth: bool = True
    half_width: bool = False
    half_slot: str = Field(default="full", max_length=16)
    power_w: float = Field(default=0.0, ge=0.0, le=50000.0)
    status: str = Field(default="active", max_length=24)
    serial: str = Field(default="", max_length=120)
    color: str = Field(default="#0284c7", max_length=32)
    front_image: str = Field(default="", max_length=300)
    rear_image: str = Field(default="", max_length=300)
    notes: Optional[str] = None
    ports_json: Optional[dict] = None


class RackDeviceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    device_type: Optional[str] = Field(default=None, max_length=40)
    manufacturer: Optional[str] = Field(default=None, max_length=80)
    model: Optional[str] = Field(default=None, max_length=120)
    slug: Optional[str] = Field(default=None, max_length=140)
    u_height: Optional[int] = Field(default=None, ge=1, le=70)
    u_position: Optional[int] = Field(default=None, ge=1, le=70)
    face: Optional[str] = Field(default=None, max_length=16)
    is_full_depth: Optional[bool] = None
    half_width: Optional[bool] = None
    half_slot: Optional[str] = Field(default=None, max_length=16)
    power_w: Optional[float] = Field(default=None, ge=0.0, le=50000.0)
    status: Optional[str] = Field(default=None, max_length=24)
    serial: Optional[str] = Field(default=None, max_length=120)
    color: Optional[str] = Field(default=None, max_length=32)
    front_image: Optional[str] = Field(default=None, max_length=300)
    rear_image: Optional[str] = Field(default=None, max_length=300)
    notes: Optional[str] = None
    ports_json: Optional[dict] = None


class DeviceTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    device_type: str = Field(default="server", max_length=40)
    manufacturer: str = Field(default="", max_length=80)
    model: str = Field(default="", max_length=120)
    slug: str = Field(default="", max_length=140)
    u_height: int = Field(default=1, ge=1, le=70)
    is_full_depth: bool = True
    half_width: bool = False
    power_w: float = Field(default=0.0, ge=0.0, le=50000.0)
    color: str = Field(default="#0284c7", max_length=32)
    front_image: str = Field(default="", max_length=300)
    rear_image: str = Field(default="", max_length=300)
    notes: Optional[str] = None


class NetboxImportRequest(BaseModel):
    data: str = Field(..., min_length=2)


# ── Serialization, Audit & Floor-Plan Sync Helpers ──────────────────────────

def _serialize_device(d: RackDevice) -> Dict[str, Any]:
    return {
        "id": d.id,
        "rack_id": d.rack_id,
        "name": d.name,
        "device_type": d.device_type,
        "manufacturer": d.manufacturer,
        "model": d.model,
        "slug": getattr(d, "slug", "") or "",
        "u_height": d.u_height,
        "u_position": d.u_position,
        "face": d.face,
        "is_full_depth": bool(getattr(d, "is_full_depth", d.face == "both")),
        "half_width": bool(d.half_width),
        "half_slot": d.half_slot,
        "power_w": float(d.power_w or 0.0),
        "status": d.status,
        "serial": d.serial,
        "color": d.color,
        "front_image": getattr(d, "front_image", "") or "",
        "rear_image": getattr(d, "rear_image", "") or "",
        "notes": d.notes or "",
        "ports_json": d.ports_json,
    }


def _serialize_rack(r: Rack) -> Dict[str, Any]:
    devs = [_serialize_device(d) for d in (r.devices or [])]
    return {
        "id": r.id,
        "furniture_id": r.furniture_id,
        "name": r.name,
        "floor_id": r.floor_id,
        "room_id": r.room_id,
        "u_height": r.u_height,
        "width_in": float(r.width_in or 19.0),
        "depth_mm": int(r.depth_mm or 1000),
        "color": r.color or "#1e293b",
        "pos_x": float(r.pos_x or 0.0),
        "pos_z": float(r.pos_z or 0.0),
        "rotation": float(r.rotation or 0.0),
        "max_power_w": float(r.max_power_w or 5000.0),
        "notes": r.notes or "",
        "devices": devs,
        "utilization": compute_rack_utilization(r.u_height, r.max_power_w, devs),
    }


def _serialize_template(t: RackDeviceTemplate) -> Dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "device_type": t.device_type,
        "manufacturer": t.manufacturer,
        "brand": t.manufacturer or "Custom",
        "model": t.model,
        "slug": getattr(t, "slug", "") or "",
        "u_height": t.u_height,
        "is_full_depth": bool(t.is_full_depth),
        "half_width": bool(t.half_width),
        "power_w": float(t.power_w or 0.0),
        "color": t.color,
        "front_image": getattr(t, "front_image", "") or "",
        "rear_image": getattr(t, "rear_image", "") or "",
        "notes": t.notes or "",
        "is_builtin": bool(t.is_builtin),
    }


async def _write_audit(
    db: AsyncSession,
    user: User,
    request: Optional[Request],
    action: str,
    resource_type: str,
    resource_id: Optional[str],
    details: Dict[str, Any],
) -> None:
    ip = request.client.host if (request and request.client) else ""
    ua = (request.headers.get("user-agent", "")[:250]) if request else ""
    db.add(
        AuditLog(
            user_id=user.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip,
            user_agent=ua,
        )
    )


async def _ensure_builtin_templates(db: AsyncSession) -> None:
    res = await db.execute(select(RackDeviceTemplate).limit(1))
    if res.scalar_one_or_none() is not None:
        return
    for tpl in BUILTIN_TEMPLATES:
        db.add(RackDeviceTemplate(is_builtin=True, **tpl))
    await db.commit()


def _rack_height_meters(u_height: int) -> float:
    # 1U = 44.45mm = 0.04445m, plus ~0.18m frame top/bottom
    return round(0.18 + u_height * 0.04445, 2)


async def _sync_racks_from_building(db: AsyncSession) -> None:
    """Import any rack furniture items from active_building_json that don't yet exist in `racks` table."""
    cfg_res = await db.execute(select(SystemConfig).where(SystemConfig.key == "active_3d_building"))
    cfg = cfg_res.scalar_one_or_none()
    if not cfg or not cfg.value:
        return
    try:
        payload = json.loads(cfg.value)
        building = payload.get("building") if isinstance(payload, dict) and "building" in payload else payload
        floors = building.get("floors", []) if isinstance(building, dict) else []
    except Exception:
        return

    existing_res = await db.execute(select(Rack.furniture_id).where(Rack.furniture_id.is_not(None)))
    known_fids = {row[0] for row in existing_res.all()}
    added = False
    for fl in floors:
        fl_id = fl.get("id") or "ground"
        for f in fl.get("furniture") or []:
            ftype = str(f.get("type") or "").lower()
            if "rack" not in ftype:
                continue
            fid = str(f.get("id") or "").strip()
            if not fid or fid in known_fids:
                continue
            u_h = int(f.get("u_height") or (24 if "24u" in ftype else 42))
            u_h = max(4, min(70, u_h))
            db.add(
                Rack(
                    furniture_id=fid,
                    name=str(f.get("name") or f"Rack {fid}")[:120],
                    floor_id=fl_id,
                    u_height=u_h,
                    width_in=float(f.get("width_in") or 19.0),
                    depth_mm=int(f.get("depth_mm") or round(float(f.get("d") or 1.0) * 1000)),
                    color=str(f.get("color") or "#1e293b"),
                    pos_x=float(f.get("x") or 2.0),
                    pos_z=float(f.get("z") or 2.0),
                    rotation=float(f.get("rot") or 0.0),
                )
            )
            known_fids.add(fid)
            added = True
    if added:
        await db.commit()


async def _upsert_rack_in_building_json(db: AsyncSession, rack: Rack, remove: bool = False) -> None:
    """Keep active_building_json furniture synchronized with the single DB `racks` table."""
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

    fid = rack.furniture_id or f"rack_{rack.id[:8]}"
    # Remove old copy if moving floor or deleting
    for fl in floors:
        furn = fl.get("furniture")
        if isinstance(furn, list):
            fl["furniture"] = [f for f in furn if str(f.get("id")) != fid]

    if not remove:
        target_fl = next((fl for fl in floors if fl.get("id") == rack.floor_id), floors[0])
        existing_furn = target_fl.setdefault("furniture", [])
        px = round(float(rack.pos_x), 2)
        pz = round(float(rack.pos_z), 2)
        # Avoid clipping directly on top of another rack if using default coordinates
        for _ in range(12):
            collides = any(
                abs(float(f.get("x", -999)) - px) < 0.65 and abs(float(f.get("z", -999)) - pz) < 0.85
                for f in existing_furn
                if "rack" in str(f.get("type", "")).lower()
            )
            if not collides:
                break
            px = round(px + 0.85, 2)
        rack.pos_x = px
        rack.pos_z = pz
        existing_furn.append(
            {
                "id": fid,
                "type": "pack:dcim.facility:rack_24u" if rack.u_height <= 28 else "pack:dcim.facility:rack_42u",
                "name": rack.name,
                "x": px,
                "z": pz,
                "rotation": round(float(rack.rotation), 3),
                "w": round(float(rack.width_in) * 0.0254 + 0.12, 2),
                "d": round(float(rack.depth_mm) / 1000.0, 2),
                "h": _rack_height_meters(rack.u_height),
                "u_height": rack.u_height,
                "rack_id": rack.id,
                "color": rack.color,
            }
        )

    cfg.value = json.dumps(payload)


_CATALOG_CACHE: Optional[Dict[str, Any]] = None
_CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "static" / "rack_assets" / "catalog.json"
_UPLOAD_IMG_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "uploads" / "device-images"


def _load_static_catalog() -> Dict[str, Any]:
    global _CATALOG_CACHE
    if _CATALOG_CACHE is not None:
        return _CATALOG_CACHE
    if _CATALOG_PATH.exists():
        try:
            _CATALOG_CACHE = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
            return _CATALOG_CACHE
        except Exception:
            pass
    return {"version": 1, "brands": [], "count": 0, "devices": []}


# ── Device Library Endpoints (declared before /{rack_id} path param) ────────

@router.get("/library/catalog")
async def get_device_catalog(
    brand: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:read")),
):
    """Return full branded hardware catalog (MikroTik, Sangfor, Supermicro, Dell, HPE, Juniper, etc.) + custom user templates."""
    cat = _load_static_catalog()
    devices: List[Dict[str, Any]] = list(cat.get("devices") or [])

    # Prepend user-created custom templates so they appear right in Custom / their Brand
    res = await db.execute(
        select(RackDeviceTemplate)
        .where(RackDeviceTemplate.is_builtin.is_(False))
        .order_by(RackDeviceTemplate.name)
    )
    for t in res.scalars().all():
        devices.insert(0, {
            "id": t.id,
            "slug": getattr(t, "slug", "") or f"custom-{t.id[:8]}",
            "brand": t.manufacturer or "Custom",
            "model": t.model or t.name,
            "name": t.name,
            "device_type": t.device_type,
            "category": t.device_type,
            "u_height": t.u_height,
            "is_full_depth": bool(t.is_full_depth),
            "half_width": bool(t.half_width),
            "power_w": float(t.power_w or 0.0),
            "color": t.color,
            "front_image": getattr(t, "front_image", "") or "",
            "rear_image": getattr(t, "rear_image", "") or "",
            "has_real_image": bool(getattr(t, "front_image", "")),
            "is_custom": True,
        })

    if brand:
        bl = brand.lower()
        devices = [d for d in devices if (d.get("brand") or "").lower() == bl]
    if category:
        cl = category.lower()
        devices = [d for d in devices if (d.get("device_type") or "").lower() == cl or (d.get("category") or "").lower() == cl]
    if q:
        ql = q.lower()
        devices = [
            d for d in devices
            if ql in (d.get("model") or "").lower()
            or ql in (d.get("brand") or "").lower()
            or ql in (d.get("name") or "").lower()
            or ql in (d.get("slug") or "").lower()
        ]

    brands = sorted({d.get("brand") or "Generic" for d in devices})
    return {"brands": brands, "count": len(devices), "devices": devices}


@router.post("/library/upload-image", status_code=status.HTTP_201_CREATED)
async def upload_device_image(
    file: UploadFile = File(...),
    side: str = Form("front"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:write")),
):
    """Upload a custom front or rear hardware photo (PNG/JPG/WebP, max 5MB) for custom rack devices."""
    ext = Path(file.filename or "device.png").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(status_code=400, detail="Only PNG, JPG, and WebP images are supported.")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image exceeds 5 MB limit.")
    _UPLOAD_IMG_DIR.mkdir(parents=True, exist_ok=True)
    safe_side = "rear" if side == "rear" else "front"
    fname = f"dev_{uuid.uuid4().hex[:12]}.{safe_side}{ext}"
    (_UPLOAD_IMG_DIR / fname).write_bytes(data)
    url = f"/static/uploads/device-images/{fname}"
    await _write_audit(db, current_user, request, "rack.image.upload", "rack_device_image", fname, {"side": safe_side, "url": url})
    await db.commit()
    return {"url": url, "side": safe_side}


@router.get("/library/templates")
async def list_device_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:read")),
):
    await _ensure_builtin_templates(db)
    res = await db.execute(select(RackDeviceTemplate).order_by(RackDeviceTemplate.is_builtin.desc(), RackDeviceTemplate.name))
    return {"templates": [_serialize_template(t) for t in res.scalars().all()]}


@router.post("/library/templates", status_code=status.HTTP_201_CREATED)
async def create_device_template(
    body: DeviceTemplateCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:write")),
):
    dtype = body.device_type if body.device_type in VALID_DEVICE_TYPES else "custom"
    tpl = RackDeviceTemplate(
        name=body.name.strip(),
        device_type=dtype,
        manufacturer=body.manufacturer.strip(),
        model=body.model.strip(),
        slug=body.slug.strip(),
        u_height=body.u_height,
        is_full_depth=body.is_full_depth,
        half_width=body.half_width,
        power_w=body.power_w,
        color=body.color,
        front_image=body.front_image.strip(),
        rear_image=body.rear_image.strip(),
        notes=body.notes,
        is_builtin=False,
    )
    db.add(tpl)
    await db.flush()
    await _write_audit(db, current_user, request, "rack.template.create", "rack_device_template", tpl.id, {"name": tpl.name})
    await db.commit()
    await db.refresh(tpl)
    return _serialize_template(tpl)


@router.delete("/library/templates/{template_id}")
async def delete_device_template(
    template_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:write")),
):
    res = await db.execute(select(RackDeviceTemplate).where(RackDeviceTemplate.id == template_id))
    tpl = res.scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="Device template not found")
    await _write_audit(db, current_user, request, "rack.template.delete", "rack_device_template", tpl.id, {"name": tpl.name})
    await db.delete(tpl)
    await db.commit()
    return {"status": "deleted", "id": template_id}


@router.post("/library/import-netbox", status_code=status.HTTP_201_CREATED)
async def import_netbox_device_types(
    body: NetboxImportRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:write")),
):
    """Import NetBox YAML or JSON device-type definitions into native RackDeviceTemplate rows."""
    parsed = _parse_netbox_device_types(body.data)
    if not parsed:
        raise HTTPException(status_code=400, detail="No valid NetBox device types found in payload")
    created = []
    for item in parsed:
        tpl = RackDeviceTemplate(is_builtin=False, **item)
        db.add(tpl)
        await db.flush()
        created.append(_serialize_template(tpl))
    await _write_audit(
        db,
        current_user,
        request,
        "rack.template.import_netbox",
        "rack_device_template",
        None,
        {"imported_count": len(created)},
    )
    await db.commit()
    return {"imported": len(created), "templates": created}


@router.get("/cables/summary")
async def list_cables_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:read")),
):
    """Return all cable runs and cable trays from the active floor plan DB with linked rack/device metadata."""
    cfg_res = await db.execute(select(SystemConfig).where(SystemConfig.key == "active_3d_building"))
    cfg = cfg_res.scalar_one_or_none()
    if not cfg or not cfg.value:
        return {"cables": [], "count": 0}
    try:
        payload = json.loads(cfg.value)
        building = payload.get("building") if isinstance(payload, dict) and "building" in payload else payload
        floors = building.get("floors", []) if isinstance(building, dict) else []
    except Exception:
        return {"cables": [], "count": 0}

    groups: Dict[str, Dict[str, Any]] = {}
    for fl in floors:
        fl_id = fl.get("id") or "ground"
        for f in fl.get("furniture") or []:
            ftype = str(f.get("type") or "")
            if "cable_" not in ftype:
                continue
            gid = str(f.get("cable_group") or f.get("id"))
            if gid not in groups:
                groups[gid] = {
                    "id": gid,
                    "floor_id": fl_id,
                    "name": f.get("name") or gid,
                    "cable_type": ftype.split(":")[-1],
                    "color": f.get("color") or "#ef4444",
                    "mount_y": float(f.get("mount_y") or 0.0),
                    "length_m": float(f.get("total_length_m") or 0.0),
                    "segments": 0,
                    "from_endpoint": f.get("from_endpoint"),
                    "to_endpoint": f.get("to_endpoint"),
                    "snapped_tray": bool(f.get("snapped_tray", False)),
                }
            g = groups[gid]
            g["segments"] += 1
            if not g["length_m"]:
                g["length_m"] = round(g["length_m"] + float(f.get("w") or 0.0), 2)
    cables = list(groups.values())
    return {"cables": cables, "count": len(cables)}


@router.get("/export")
async def export_racks_json(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:read")),
):
    await _sync_racks_from_building(db)
    res = await db.execute(select(Rack).options(selectinload(Rack.devices)).order_by(Rack.name))
    racks = [_serialize_rack(r) for r in res.scalars().all()]
    payload = {"version": 1, "exported_at": datetime.now(timezone.utc).isoformat(), "racks": racks}
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="racks_export.json"'},
    )


# ── Rack CRUD Endpoints ─────────────────────────────────────────────────────

@router.get("")
async def list_racks(
    floor_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:read")),
):
    await _sync_racks_from_building(db)
    stmt = select(Rack).options(selectinload(Rack.devices)).order_by(Rack.name)
    if floor_id:
        stmt = stmt.where(Rack.floor_id == floor_id)
    res = await db.execute(stmt)
    racks = [_serialize_rack(r) for r in res.scalars().all()]
    return {"racks": racks, "count": len(racks)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_rack(
    body: RackCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:write")),
):
    fid = body.furniture_id or f"rack_{uuid.uuid4().hex[:8]}"
    rack = Rack(
        furniture_id=fid,
        name=body.name.strip(),
        floor_id=body.floor_id,
        room_id=body.room_id,
        u_height=body.u_height,
        width_in=body.width_in,
        depth_mm=body.depth_mm,
        color=body.color,
        pos_x=body.pos_x,
        pos_z=body.pos_z,
        rotation=body.rotation,
        max_power_w=body.max_power_w,
        notes=body.notes,
    )
    db.add(rack)
    await db.flush()
    if body.sync_floor_plan:
        await _upsert_rack_in_building_json(db, rack, remove=False)
    await _write_audit(
        db,
        current_user,
        request,
        "rack.create",
        "rack",
        rack.id,
        {"name": rack.name, "u_height": rack.u_height, "floor_id": rack.floor_id},
    )
    await db.commit()
    res = await db.execute(select(Rack).options(selectinload(Rack.devices)).where(Rack.id == rack.id))
    out = _serialize_rack(res.scalar_one())
    await notifier.broadcast_json({"type": "rack_updated", "action": "create", "rack_id": rack.id})
    return out


@router.get("/{rack_id}")
async def get_rack(
    rack_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:read")),
):
    res = await db.execute(
        select(Rack).options(selectinload(Rack.devices)).where((Rack.id == rack_id) | (Rack.furniture_id == rack_id))
    )
    rack = res.scalar_one_or_none()
    if not rack:
        raise HTTPException(status_code=404, detail="Rack not found")
    return _serialize_rack(rack)


@router.put("/{rack_id}")
async def update_rack(
    rack_id: str,
    body: RackUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:write")),
):
    res = await db.execute(
        select(Rack).options(selectinload(Rack.devices)).where((Rack.id == rack_id) | (Rack.furniture_id == rack_id))
    )
    rack = res.scalar_one_or_none()
    if not rack:
        raise HTTPException(status_code=404, detail="Rack not found")

    if body.u_height is not None:
        # Ensure shrinking rack doesn't push existing devices out of bounds
        for d in rack.devices:
            if d.u_position + d.u_height - 1 > body.u_height:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Cannot resize rack to {body.u_height}U: '{d.name}' occupies up to U{d.u_position + d.u_height - 1}.",
                )
        rack.u_height = body.u_height

    for field in ("name", "floor_id", "room_id", "width_in", "depth_mm", "color", "pos_x", "pos_z", "rotation", "max_power_w", "notes"):
        val = getattr(body, field)
        if val is not None:
            setattr(rack, field, val.strip() if isinstance(val, str) and field == "name" else val)

    await _upsert_rack_in_building_json(db, rack, remove=False)
    await _write_audit(db, current_user, request, "rack.update", "rack", rack.id, {"name": rack.name, "u_height": rack.u_height})
    await db.commit()
    res2 = await db.execute(select(Rack).options(selectinload(Rack.devices)).where(Rack.id == rack.id))
    out = _serialize_rack(res2.scalar_one())
    await notifier.broadcast_json({"type": "rack_updated", "action": "update", "rack_id": rack.id})
    return out


@router.delete("/{rack_id}")
async def delete_rack(
    rack_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:write")),
):
    res = await db.execute(select(Rack).where((Rack.id == rack_id) | (Rack.furniture_id == rack_id)))
    rack = res.scalar_one_or_none()
    if not rack:
        raise HTTPException(status_code=404, detail="Rack not found")
    await _upsert_rack_in_building_json(db, rack, remove=True)
    await _write_audit(db, current_user, request, "rack.delete", "rack", rack.id, {"name": rack.name})
    await db.delete(rack)
    await db.commit()
    await notifier.broadcast_json({"type": "rack_updated", "action": "delete", "rack_id": rack_id})
    return {"status": "deleted", "id": rack.id}


# ── Rack Device Elevation CRUD (with Overlap & Bounds Validation) ───────────

@router.post("/{rack_id}/devices", status_code=status.HTTP_201_CREATED)
async def add_rack_device(
    rack_id: str,
    body: RackDeviceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:write")),
):
    res = await db.execute(
        select(Rack).options(selectinload(Rack.devices)).where((Rack.id == rack_id) | (Rack.furniture_id == rack_id))
    )
    rack = res.scalar_one_or_none()
    if not rack:
        raise HTTPException(status_code=404, detail="Rack not found")

    face = body.face if body.face in VALID_FACES else "front"
    half_slot = body.half_slot if (body.half_width and body.half_slot in ("left", "right")) else ("left" if body.half_width else "full")
    dtype = body.device_type if body.device_type in VALID_DEVICE_TYPES else "custom"
    dstatus = body.status if body.status in VALID_STATUSES else "active"

    ok, err = validate_rack_device_placement(
        rack_u_height=rack.u_height,
        existing_devices=[_serialize_device(d) for d in rack.devices],
        u_position=body.u_position,
        u_height=body.u_height,
        face=face,
        half_width=body.half_width,
        half_slot=half_slot,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err)

    dev = RackDevice(
        rack_id=rack.id,
        name=body.name.strip(),
        device_type=dtype,
        manufacturer=body.manufacturer.strip(),
        model=body.model.strip(),
        slug=body.slug.strip(),
        u_height=body.u_height,
        u_position=body.u_position,
        face=face,
        is_full_depth=body.is_full_depth,
        half_width=body.half_width,
        half_slot=half_slot,
        power_w=body.power_w,
        status=dstatus,
        serial=body.serial.strip(),
        color=body.color,
        front_image=body.front_image.strip(),
        rear_image=body.rear_image.strip(),
        notes=body.notes,
        ports_json=body.ports_json,
    )
    db.add(dev)
    await db.flush()
    await _write_audit(
        db,
        current_user,
        request,
        "rack.device.add",
        "rack_device",
        dev.id,
        {"rack_id": rack.id, "name": dev.name, "u_position": dev.u_position, "u_height": dev.u_height, "face": dev.face},
    )
    await db.commit()
    await db.refresh(dev)
    await notifier.broadcast_json({"type": "rack_updated", "action": "device_add", "rack_id": rack.id})
    return _serialize_device(dev)


@router.put("/{rack_id}/devices/{device_id}")
async def update_rack_device(
    rack_id: str,
    device_id: str,
    body: RackDeviceUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:write")),
):
    res = await db.execute(
        select(Rack).options(selectinload(Rack.devices)).where((Rack.id == rack_id) | (Rack.furniture_id == rack_id))
    )
    rack = res.scalar_one_or_none()
    if not rack:
        raise HTTPException(status_code=404, detail="Rack not found")
    dev = next((d for d in rack.devices if d.id == device_id), None)
    if not dev:
        raise HTTPException(status_code=404, detail="Rack device not found")

    cand_pos = body.u_position if body.u_position is not None else dev.u_position
    cand_h = body.u_height if body.u_height is not None else dev.u_height
    cand_face = body.face if (body.face in VALID_FACES) else dev.face
    cand_half = body.half_width if body.half_width is not None else bool(dev.half_width)
    cand_slot = body.half_slot if (body.half_slot in VALID_HALF_SLOTS) else dev.half_slot
    if not cand_half:
        cand_slot = "full"
    elif cand_slot not in ("left", "right"):
        cand_slot = "left"

    ok, err = validate_rack_device_placement(
        rack_u_height=rack.u_height,
        existing_devices=[_serialize_device(d) for d in rack.devices],
        u_position=cand_pos,
        u_height=cand_h,
        face=cand_face,
        half_width=cand_half,
        half_slot=cand_slot,
        ignore_device_id=dev.id,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err)

    dev.u_position = cand_pos
    dev.u_height = cand_h
    dev.face = cand_face
    dev.half_width = cand_half
    dev.half_slot = cand_slot
    if body.name is not None:
        dev.name = body.name.strip()
    if body.device_type in VALID_DEVICE_TYPES:
        dev.device_type = body.device_type
    if body.manufacturer is not None:
        dev.manufacturer = body.manufacturer.strip()
    if body.model is not None:
        dev.model = body.model.strip()
    if body.slug is not None:
        dev.slug = body.slug.strip()
    if body.is_full_depth is not None:
        dev.is_full_depth = body.is_full_depth
    if body.power_w is not None:
        dev.power_w = body.power_w
    if body.status in VALID_STATUSES:
        dev.status = body.status
    if body.serial is not None:
        dev.serial = body.serial.strip()
    if body.color is not None:
        dev.color = body.color
    if body.front_image is not None:
        dev.front_image = body.front_image.strip()
    if body.rear_image is not None:
        dev.rear_image = body.rear_image.strip()
    if body.notes is not None:
        dev.notes = body.notes
    if body.ports_json is not None:
        dev.ports_json = body.ports_json

    await _write_audit(
        db,
        current_user,
        request,
        "rack.device.update",
        "rack_device",
        dev.id,
        {"rack_id": rack.id, "name": dev.name, "u_position": dev.u_position, "u_height": dev.u_height},
    )
    await db.commit()
    await db.refresh(dev)
    await notifier.broadcast_json({"type": "rack_updated", "action": "device_update", "rack_id": rack.id})
    return _serialize_device(dev)


@router.delete("/{rack_id}/devices/{device_id}")
async def delete_rack_device(
    rack_id: str,
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("racks:write")),
):
    res = await db.execute(
        select(Rack).options(selectinload(Rack.devices)).where((Rack.id == rack_id) | (Rack.furniture_id == rack_id))
    )
    rack = res.scalar_one_or_none()
    if not rack:
        raise HTTPException(status_code=404, detail="Rack not found")
    dev = next((d for d in rack.devices if d.id == device_id), None)
    if not dev:
        raise HTTPException(status_code=404, detail="Rack device not found")
    await _write_audit(db, current_user, request, "rack.device.delete", "rack_device", dev.id, {"rack_id": rack.id, "name": dev.name})
    await db.delete(dev)
    await db.commit()
    await notifier.broadcast_json({"type": "rack_updated", "action": "device_delete", "rack_id": rack.id})
    return {"status": "deleted", "id": device_id}
