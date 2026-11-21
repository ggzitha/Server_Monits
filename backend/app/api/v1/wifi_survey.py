"""
wifi_survey.py - Wi-Fi Survey RSSI Measurement & AP/SSID Heatmap API (Phase 4)
Single source of truth for measured Wi-Fi RSSI points (SSID, BSSID, Band 2.4/5/6 GHz,
Channel, Signal Strength in dBm, 3D coordinates) with automatic migration, AP summary
metadata, and JSON/CSV import & export.
"""
import csv
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user, get_db
from backend.app.db.models.system_config import SystemConfig
from backend.app.services.notifier import notifier

router = APIRouter(prefix="/wifi-survey", tags=["wifi-survey"])

WIFI_SURVEY_CONFIG_KEY = "wifi_survey_points"
VALID_BANDS = {"2.4GHz", "5GHz", "6GHz", "N/A"}


def _normalize_band(band: Optional[str], channel: Optional[int] = None) -> str:
    raw = (band or "").strip().lower().replace(" ", "")
    if raw in ("2.4", "2.4g", "2.4ghz", "2g"):
        return "2.4GHz"
    if raw in ("5", "5g", "5ghz"):
        return "5GHz"
    if raw in ("6", "6g", "6ghz"):
        return "6GHz"
    if raw in ("n/a", "na", "unknown"):
        return "N/A"
    if channel is not None:
        if 1 <= channel <= 14:
            return "2.4GHz"
        if 32 <= channel <= 177:
            return "5GHz"
        if channel > 177:
            return "6GHz"
    return "5GHz"


def _default_channel_for_band(band: str) -> Optional[int]:
    if band == "2.4GHz":
        return 6
    if band == "5GHz":
        return 36
    if band == "6GHz":
        return 37
    return None


def _migrate_point(p: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    """Ensure legacy points have normalized band and optional channel fields."""
    changed = False
    out = dict(p)
    ch = out.get("channel")
    if ch is not None and ch != "":
        try:
            ch_int = int(ch)
            if out.get("channel") != ch_int:
                out["channel"] = ch_int
                changed = True
        except (TypeError, ValueError):
            out["channel"] = None
            changed = True
    else:
        if "channel" not in out:
            out["channel"] = None
            changed = True

    norm_band = _normalize_band(out.get("band"), out.get("channel"))
    if out.get("band") != norm_band:
        out["band"] = norm_band
        changed = True
    return out, changed


def _build_ap_summaries(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate unique AP/SSID entries with all observed bands and channels."""
    by_ssid: Dict[str, Dict[str, Any]] = {}
    for p in points:
        ssid = str(p.get("ssid") or "").strip()
        if not ssid:
            continue
        rec = by_ssid.setdefault(ssid, {"ssid": ssid, "bands": set(), "channels": set(), "count": 0})
        b = _normalize_band(p.get("band"), p.get("channel"))
        if b != "N/A":
            rec["bands"].add(b)
        if p.get("channel") is not None:
            rec["channels"].add(int(p["channel"]))
        rec["count"] += 1

    band_order = {"2.4GHz": 0, "5GHz": 1, "6GHz": 2, "N/A": 3}
    summaries = []
    for ssid in sorted(by_ssid.keys(), key=str.lower):
        rec = by_ssid[ssid]
        bands = sorted(rec["bands"], key=lambda x: band_order.get(x, 9))
        channels = sorted(rec["channels"])
        band_str = " / ".join(b.replace("GHz", " GHz") for b in bands) if bands else "N/A"
        ch_str = f" ch{','.join(str(c) for c in channels)}" if channels else ""
        summaries.append(
            {
                "ssid": ssid,
                "bands": bands,
                "channels": channels,
                "count": rec["count"],
                "label": f"{ssid} — {band_str}{ch_str}",
            }
        )
    return summaries


class WifiSurveyPointCreate(BaseModel):
    ssid: str = Field(..., min_length=1, max_length=120)
    rssi_dbm: float = Field(..., ge=-120.0, le=0.0)
    floor_id: str = Field(default="ground", max_length=64)
    x: float
    z: float
    y: float = 1.2
    bssid: Optional[str] = Field(default=None, max_length=64)
    band: str = Field(default="5GHz", max_length=16)
    channel: Optional[int] = Field(default=None, ge=1, le=233)
    notes: Optional[str] = Field(default=None, max_length=300)


class WifiSurveyPointUpdate(BaseModel):
    ssid: Optional[str] = Field(default=None, min_length=1, max_length=120)
    rssi_dbm: Optional[float] = Field(default=None, ge=-120.0, le=0.0)
    floor_id: Optional[str] = Field(default=None, max_length=64)
    x: Optional[float] = None
    z: Optional[float] = None
    y: Optional[float] = None
    bssid: Optional[str] = Field(default=None, max_length=64)
    band: Optional[str] = Field(default=None, max_length=16)
    channel: Optional[int] = Field(default=None, ge=1, le=233)
    notes: Optional[str] = Field(default=None, max_length=300)


class WifiSurveyBatchUpload(BaseModel):
    points: List[WifiSurveyPointCreate] = Field(..., min_length=1, max_length=500)


class WifiSurveyImportPayload(BaseModel):
    format: str = Field(default="json", pattern="^(json|csv)$")
    data: Any
    replace: bool = False


async def _load_points(db: AsyncSession) -> List[Dict[str, Any]]:
    res = await db.execute(select(SystemConfig).where(SystemConfig.key == WIFI_SURVEY_CONFIG_KEY))
    cfg = res.scalar_one_or_none()
    if not cfg or not cfg.value:
        return []
    try:
        parsed = json.loads(cfg.value)
        if not isinstance(parsed, list):
            return []
        migrated = []
        any_changed = False
        for item in parsed:
            if not isinstance(item, dict):
                continue
            m_item, chg = _migrate_point(item)
            migrated.append(m_item)
            any_changed = any_changed or chg
        if any_changed:
            cfg.value = json.dumps(migrated)
            await db.commit()
        return migrated
    except Exception:
        return []


async def _save_points(db: AsyncSession, points: List[Dict[str, Any]]) -> None:
    res = await db.execute(select(SystemConfig).where(SystemConfig.key == WIFI_SURVEY_CONFIG_KEY))
    cfg = res.scalar_one_or_none()
    serialized = json.dumps(points)
    if not cfg:
        db.add(SystemConfig(key=WIFI_SURVEY_CONFIG_KEY, value=serialized))
    else:
        cfg.value = serialized
    await db.commit()


def _make_record(item: WifiSurveyPointCreate) -> Dict[str, Any]:
    band = _normalize_band(item.band, item.channel)
    ch = item.channel if item.channel is not None else _default_channel_for_band(band)
    return {
        "id": str(uuid.uuid4()),
        "ssid": item.ssid.strip(),
        "bssid": (item.bssid or "").strip() or None,
        "band": band,
        "channel": ch,
        "rssi_dbm": round(float(item.rssi_dbm), 1),
        "floor_id": item.floor_id or "ground",
        "x": round(float(item.x), 2),
        "z": round(float(item.z), 2),
        "y": round(float(item.y), 2),
        "notes": (item.notes or "").strip() or None,
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("")
async def list_wifi_survey_points(
    ssid: Optional[str] = Query(default=None),
    band: Optional[str] = Query(default=None),
    channel: Optional[int] = Query(default=None),
    floor_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List Wi-Fi survey RSSI points, distinct AP/SSID summaries (with bands/channels), and filters."""
    all_points = await _load_points(db)
    aps = _build_ap_summaries(all_points)
    ssids = [a["ssid"] for a in aps]
    bands = sorted({p.get("band") for p in all_points if p.get("band") and p.get("band") != "N/A"})
    channels = sorted({int(p["channel"]) for p in all_points if p.get("channel") is not None})

    filtered = all_points
    if ssid:
        filtered = [p for p in filtered if p.get("ssid") == ssid]
    if band:
        nb = _normalize_band(band)
        filtered = [p for p in filtered if p.get("band") == nb]
    if channel is not None:
        filtered = [p for p in filtered if p.get("channel") == channel]
    if floor_id:
        filtered = [p for p in filtered if p.get("floor_id") == floor_id]
    return {
        "points": filtered,
        "ssids": ssids,
        "aps": aps,
        "bands": bands,
        "channels": channels,
        "total": len(filtered),
    }


@router.get("/export")
async def export_wifi_survey(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Export all Wi-Fi RSSI survey points (including band and channel) as JSON or CSV."""
    points = await _load_points(db)
    if format == "csv":
        buf = io.StringIO()
        fields = ["id", "ssid", "bssid", "band", "channel", "rssi_dbm", "floor_id", "x", "z", "y", "notes", "measured_at"]
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for p in points:
            writer.writerow(p)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="wifi_survey_rssi.csv"'},
        )
    return {"version": 1, "exported_at": datetime.now(timezone.utc).isoformat(), "points": points}


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_wifi_survey(
    payload: WifiSurveyImportPayload,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Import Wi-Fi RSSI survey points from JSON or CSV (preserving band and channel)."""
    raw_items: List[Dict[str, Any]] = []
    if payload.format == "csv":
        if not isinstance(payload.data, str):
            raise HTTPException(status_code=400, detail="CSV import expects a text string in 'data'")
        reader = csv.DictReader(io.StringIO(payload.data))
        for row in reader:
            if not row.get("ssid"):
                continue
            raw_items.append(
                {
                    "ssid": row["ssid"],
                    "bssid": row.get("bssid") or None,
                    "band": row.get("band") or "5GHz",
                    "channel": int(row["channel"]) if row.get("channel") not in (None, "") else None,
                    "rssi_dbm": float(row.get("rssi_dbm", -65)),
                    "floor_id": row.get("floor_id") or "ground",
                    "x": float(row.get("x", 0)),
                    "z": float(row.get("z", 0)),
                    "y": float(row.get("y", 1.2)),
                    "notes": row.get("notes") or None,
                }
            )
    else:
        src = payload.data.get("points") if isinstance(payload.data, dict) else payload.data
        if not isinstance(src, list):
            raise HTTPException(status_code=400, detail="JSON import expects a list of points or {points: [...]}")
        raw_items = [item for item in src if isinstance(item, dict) and item.get("ssid")]

    existing = [] if payload.replace else await _load_points(db)
    added = []
    for item in raw_items:
        model = WifiSurveyPointCreate(**item)
        rec = _make_record(model)
        existing.append(rec)
        added.append(rec)
    await _save_points(db, existing)
    await notifier.broadcast_json({"type": "wifi_survey_updated", "action": "import", "count": len(added)})
    return {"status": "ok", "imported": len(added), "total": len(existing)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_wifi_survey_point(
    data: WifiSurveyPointCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Add a single Wi-Fi RSSI survey point."""
    points = await _load_points(db)
    rec = _make_record(data)
    points.append(rec)
    await _save_points(db, points)
    await notifier.broadcast_json({"type": "wifi_survey_updated", "action": "add", "point": rec})
    return rec


@router.post("/batch", status_code=status.HTTP_201_CREATED)
async def batch_upload_wifi_survey(
    payload: WifiSurveyBatchUpload,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Upload a batch of Wi-Fi RSSI survey points (used by survey-agent CLI)."""
    points = await _load_points(db)
    added = [_make_record(item) for item in payload.points]
    points.extend(added)
    await _save_points(db, points)
    await notifier.broadcast_json({"type": "wifi_survey_updated", "action": "batch", "count": len(added)})
    return {"status": "ok", "added": len(added), "points": added}


@router.put("/{point_id}")
async def update_wifi_survey_point(
    point_id: str,
    data: WifiSurveyPointUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update an existing Wi-Fi RSSI survey point (including Band and Channel)."""
    points = await _load_points(db)
    target = next((p for p in points if p.get("id") == point_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Wi-Fi survey point not found")

    if data.ssid is not None:
        target["ssid"] = data.ssid.strip()
    if data.rssi_dbm is not None:
        target["rssi_dbm"] = round(float(data.rssi_dbm), 1)
    if data.floor_id is not None:
        target["floor_id"] = data.floor_id
    if data.x is not None:
        target["x"] = round(float(data.x), 2)
    if data.z is not None:
        target["z"] = round(float(data.z), 2)
    if data.y is not None:
        target["y"] = round(float(data.y), 2)
    if data.bssid is not None:
        target["bssid"] = data.bssid.strip() or None
    if data.channel is not None:
        target["channel"] = int(data.channel)
    if data.band is not None:
        target["band"] = _normalize_band(data.band, target.get("channel"))
    if data.notes is not None:
        target["notes"] = data.notes.strip() or None
    target["measured_at"] = datetime.now(timezone.utc).isoformat()

    await _save_points(db, points)
    await notifier.broadcast_json({"type": "wifi_survey_updated", "action": "update", "point": target})
    return target


@router.delete("/{point_id}")
async def delete_wifi_survey_point(
    point_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a single Wi-Fi RSSI survey point."""
    points = await _load_points(db)
    new_points = [p for p in points if p.get("id") != point_id]
    if len(new_points) == len(points):
        raise HTTPException(status_code=404, detail="Wi-Fi survey point not found")
    await _save_points(db, new_points)
    await notifier.broadcast_json({"type": "wifi_survey_updated", "action": "delete", "id": point_id})
    return {"status": "deleted", "id": point_id}
