"""
alerts.py - Phase 7 Alerting, Threshold Rules, Incident Timeline & Exportable Reports API.

- Full CRUD for AlertRule (`alert_rules`)
- Full CRUD for Alert Incidents (`alerts`) + unified view with SecurityEvent alerts
- Live Threshold Evaluator (`POST /api/v1/alerts/evaluate`)
- Exportable DCIM Executive & SLA Reports (JSON, CSV, Printable HTML/PDF)
- Enforces RBAC (`sensors:read` / `sensors:write`), AuditLog, and WebSocket notifications.
"""
import csv
import html
import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.deps import get_db, require_permission
from backend.app.db.models.alert import Alert, AlertRule
from backend.app.db.models.audit import AuditLog
from backend.app.db.models.rack import Rack, RackCable
from backend.app.db.models.security import SecurityDevice, SecurityEvent
from backend.app.db.models.sensor import Sensor
from backend.app.db.models.user import User
from backend.app.services.notifier import notifier

router = APIRouter(prefix="/alerts", tags=["alerts"])

VALID_SCOPES = {"all_sensors", "sensor", "rack_power", "security"}
VALID_METRICS = {"temperature", "humidity", "power_kw", "rack_power_pct"}
VALID_OPERATORS = {"gt", "gte", "lt", "lte"}
VALID_SEVERITIES = {"warning", "critical"}
VALID_INCIDENT_STATUSES = {"active", "acknowledged", "resolved"}

DEFAULT_ALERT_RULES: List[Dict[str, Any]] = [
    {
        "name": "ASHRAE High Temperature",
        "enabled": True,
        "target_scope": "all_sensors",
        "metric_type": "temperature",
        "operator": "gt",
        "warning_threshold": 27.0,
        "critical_threshold": 30.0,
        "cooldown_minutes": 15,
        "description": "Triggers when cold/hot aisle temperature exceeds ASHRAE recommended envelope.",
    },
    {
        "name": "High Relative Humidity",
        "enabled": True,
        "target_scope": "all_sensors",
        "metric_type": "humidity",
        "operator": "gt",
        "warning_threshold": 65.0,
        "critical_threshold": 75.0,
        "cooldown_minutes": 15,
        "description": "Prevents condensation risk inside server cabinets.",
    },
    {
        "name": "Low Humidity (ESD Risk)",
        "enabled": True,
        "target_scope": "all_sensors",
        "metric_type": "humidity",
        "operator": "lt",
        "warning_threshold": 30.0,
        "critical_threshold": 20.0,
        "cooldown_minutes": 15,
        "description": "Protects hardware from electrostatic discharge in dry environments.",
    },
]


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=140)
    enabled: bool = True
    target_scope: str = Field(default="all_sensors", max_length=32)
    target_id: Optional[str] = Field(default=None, max_length=100)
    metric_type: str = Field(default="temperature", max_length=40)
    operator: str = Field(default="gt", max_length=12)
    warning_threshold: Optional[float] = None
    critical_threshold: float = 30.0
    cooldown_minutes: int = Field(default=15, ge=1, le=1440)
    notify_webhook_url: str = Field(default="", max_length=500)
    description: Optional[str] = None


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=140)
    enabled: Optional[bool] = None
    target_scope: Optional[str] = Field(default=None, max_length=32)
    target_id: Optional[str] = Field(default=None, max_length=100)
    metric_type: Optional[str] = Field(default=None, max_length=40)
    operator: Optional[str] = Field(default=None, max_length=12)
    warning_threshold: Optional[float] = None
    critical_threshold: Optional[float] = None
    cooldown_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    notify_webhook_url: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = None


class IncidentCreate(BaseModel):
    sensor_id: str = Field(min_length=1, max_length=36)
    metric_type: str = Field(default="temperature", max_length=50)
    severity: str = Field(default="warning", max_length=20)
    reading_value: float = 0.0
    threshold_value: float = 0.0
    message: str = Field(min_length=1, max_length=255)
    comment: Optional[str] = None


class IncidentUpdate(BaseModel):
    status: Optional[str] = Field(default=None, max_length=30)
    severity: Optional[str] = Field(default=None, max_length=20)
    message: Optional[str] = Field(default=None, max_length=255)
    comment: Optional[str] = None


def evaluate_rule_value(
    value: Optional[float],
    operator: str,
    warning_threshold: Optional[float],
    critical_threshold: float,
) -> Tuple[Optional[str], Optional[float]]:
    """
    Pure threshold evaluator.
    Returns `(severity, breached_threshold)` where severity is `'critical'`, `'warning'`, or `None`.
    """
    if value is None:
        return None, None

    def _cmp(v: float, th: float) -> bool:
        if operator == "gt":
            return v > th
        if operator == "gte":
            return v >= th
        if operator == "lt":
            return v < th
        if operator == "lte":
            return v <= th
        return False

    if _cmp(float(value), float(critical_threshold)):
        return "critical", float(critical_threshold)
    if warning_threshold is not None and _cmp(float(value), float(warning_threshold)):
        return "warning", float(warning_threshold)
    return None, None


def _serialize_rule(r: AlertRule) -> Dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "enabled": bool(r.enabled),
        "target_scope": r.target_scope,
        "target_id": r.target_id,
        "metric_type": r.metric_type,
        "operator": r.operator,
        "warning_threshold": r.warning_threshold,
        "critical_threshold": r.critical_threshold,
        "cooldown_minutes": r.cooldown_minutes,
        "notify_webhook_url": r.notify_webhook_url or "",
        "description": r.description or "",
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _serialize_incident(a: Alert, sensor_map: Dict[str, Sensor]) -> Dict[str, Any]:
    s = sensor_map.get(a.sensor_id)
    return {
        "id": a.id,
        "source": "environment",
        "sensor_id": a.sensor_id,
        "sensor_name": s.name if s else a.sensor_id,
        "sensor_identifier": s.identifier if s else "",
        "metric_type": a.metric_type,
        "severity": a.severity,
        "reading_value": round(float(a.reading_value), 2),
        "threshold_value": round(float(a.threshold_value), 2),
        "message": a.message,
        "status": a.status,
        "acknowledged_by": a.acknowledged_by,
        "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        "comment": a.comment or "",
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


async def _write_audit(
    db: AsyncSession,
    user: User,
    request: Request,
    action: str,
    resource_type: str,
    resource_id: Optional[str],
    details: Dict[str, Any],
) -> None:
    db.add(
        AuditLog(
            user_id=user.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=request.client.host if request.client else "127.0.0.1",
            user_agent=request.headers.get("user-agent", "")[:255],
            details=details,
        )
    )


async def _ensure_default_rules(db: AsyncSession) -> List[AlertRule]:
    rows = (await db.execute(select(AlertRule).order_by(AlertRule.created_at.asc()))).scalars().all()
    if rows:
        return list(rows)
    created = [AlertRule(**spec) for spec in DEFAULT_ALERT_RULES]
    db.add_all(created)
    await db.commit()
    return created


# ── Threshold Alert Rules (Full CRUD) ───────────────────────────────────────

@router.get("/rules")
async def list_alert_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("sensors:read")),
):
    rules = await _ensure_default_rules(db)
    return {"rules": [_serialize_rule(r) for r in rules], "count": len(rules)}


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    body: AlertRuleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("sensors:write")),
):
    if body.target_scope not in VALID_SCOPES:
        raise HTTPException(status_code=400, detail=f"Invalid target_scope '{body.target_scope}'")
    if body.metric_type not in VALID_METRICS:
        raise HTTPException(status_code=400, detail=f"Invalid metric_type '{body.metric_type}'")
    if body.operator not in VALID_OPERATORS:
        raise HTTPException(status_code=400, detail=f"Invalid operator '{body.operator}'")

    rule = AlertRule(
        name=body.name.strip(),
        enabled=body.enabled,
        target_scope=body.target_scope,
        target_id=body.target_id,
        metric_type=body.metric_type,
        operator=body.operator,
        warning_threshold=body.warning_threshold,
        critical_threshold=body.critical_threshold,
        cooldown_minutes=body.cooldown_minutes,
        notify_webhook_url=body.notify_webhook_url.strip(),
        description=body.description,
    )
    db.add(rule)
    await db.flush()
    await _write_audit(db, current_user, request, "alert.rule.create", "alert_rule", rule.id, {"name": rule.name})
    await db.commit()
    return _serialize_rule(rule)


@router.patch("/rules/{rule_id}")
async def update_alert_rule(
    rule_id: str,
    body: AlertRuleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("sensors:write")),
):
    rule = (await db.execute(select(AlertRule).where(AlertRule.id == rule_id))).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    for fld in ("name", "enabled", "target_scope", "target_id", "metric_type", "operator", "warning_threshold", "critical_threshold", "cooldown_minutes", "notify_webhook_url", "description"):
        val = getattr(body, fld)
        if val is not None:
            if fld == "target_scope" and val not in VALID_SCOPES:
                raise HTTPException(status_code=400, detail=f"Invalid target_scope '{val}'")
            if fld == "metric_type" and val not in VALID_METRICS:
                raise HTTPException(status_code=400, detail=f"Invalid metric_type '{val}'")
            if fld == "operator" and val not in VALID_OPERATORS:
                raise HTTPException(status_code=400, detail=f"Invalid operator '{val}'")
            setattr(rule, fld, val.strip() if isinstance(val, str) else val)
    await _write_audit(db, current_user, request, "alert.rule.update", "alert_rule", rule.id, {"name": rule.name})
    await db.commit()
    return _serialize_rule(rule)


@router.delete("/rules/{rule_id}")
async def delete_alert_rule(
    rule_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("sensors:write")),
):
    rule = (await db.execute(select(AlertRule).where(AlertRule.id == rule_id))).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    name = rule.name
    await db.delete(rule)
    await _write_audit(db, current_user, request, "alert.rule.delete", "alert_rule", rule_id, {"name": name})
    await db.commit()
    return {"deleted": True, "id": rule_id}


# ── Threshold Rule Evaluator ────────────────────────────────────────────────

@router.post("/evaluate")
async def evaluate_alert_rules(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("sensors:write")),
):
    """Evaluate all enabled AlertRules against current DB sensor readings and open incidents on breach."""
    rules = [r for r in await _ensure_default_rules(db) if r.enabled]
    sensors = (await db.execute(select(Sensor))).scalars().all()
    active_alerts = (await db.execute(select(Alert).where(Alert.status == "active"))).scalars().all()
    active_keys = {(a.sensor_id, a.metric_type) for a in active_alerts}

    created_alerts: List[Alert] = []
    for r in rules:
        if r.target_scope not in ("all_sensors", "sensor"):
            continue
        target_sensors = (
            [s for s in sensors if s.id == r.target_id or s.identifier == r.target_id]
            if r.target_scope == "sensor" and r.target_id
            else sensors
        )
        for s in target_sensors:
            val: Optional[float] = None
            unit = ""
            if r.metric_type == "temperature":
                val = s.current_temperature
                unit = "°C"
            elif r.metric_type == "humidity":
                val = s.current_humidity
                unit = "%RH"
            elif r.metric_type == "power_kw":
                meta = s.metadata_json or {}
                val = float(meta["power_kw"]) if meta.get("power_kw") is not None else None
                unit = "kW"

            sev, th = evaluate_rule_value(val, r.operator, r.warning_threshold, r.critical_threshold)
            if sev and th is not None and (s.id, r.metric_type) not in active_keys:
                alert = Alert(
                    sensor_id=s.id,
                    metric_type=r.metric_type,
                    severity=sev,
                    reading_value=float(val),
                    threshold_value=float(th),
                    message=f"[{r.name}] {s.name}: {float(val):.1f}{unit} ({r.operator} {th:.1f}{unit})",
                    status="active",
                )
                db.add(alert)
                created_alerts.append(alert)
                active_keys.add((s.id, r.metric_type))

    if created_alerts:
        await db.flush()
        await _write_audit(db, current_user, request, "alert.evaluate", "alert", None, {"triggered": len(created_alerts)})
    await db.commit()
    sensor_map = {s.id: s for s in sensors}
    if created_alerts:
        await notifier.broadcast_json({"type": "alerts_evaluated", "triggered": len(created_alerts)})
    return {
        "evaluated_rules": len(rules),
        "evaluated_sensors": len(sensors),
        "triggered": len(created_alerts),
        "incidents": [_serialize_incident(a, sensor_map) for a in created_alerts],
    }


# ── Incident Timeline (Full CRUD) ───────────────────────────────────────────

@router.get("/incidents")
async def list_incidents(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    severity: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("sensors:read")),
):
    stmt = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(Alert.status == status_filter)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    alerts = (await db.execute(stmt)).scalars().all()
    sensors = (await db.execute(select(Sensor))).scalars().all()
    sensor_map = {s.id: s for s in sensors}
    items = [_serialize_incident(a, sensor_map) for a in alerts]

    # Also include recent warning/critical SecurityEvents for unified timeline visibility
    sec_events = (await db.execute(
        select(SecurityEvent)
        .where(SecurityEvent.severity.in_(("warning", "critical")))
        .order_by(SecurityEvent.created_at.desc())
        .limit(30)
    )).scalars().all()
    sec_devs = {d.id: d for d in (await db.execute(select(SecurityDevice))).scalars().all()}
    sec_items = []
    for ev in sec_devs and sec_events or []:
        st = "resolved" if ev.acknowledged else "active"
        if status_filter and st != status_filter:
            continue
        if severity and ev.severity != severity:
            continue
        dev = sec_devs.get(ev.device_id)
        sec_items.append({
            "id": ev.id,
            "source": "security",
            "sensor_id": ev.device_id,
            "sensor_name": dev.name if dev else ev.device_id,
            "sensor_identifier": dev.entity_id if dev else "",
            "metric_type": ev.event_type,
            "severity": ev.severity,
            "reading_value": None,
            "threshold_value": None,
            "message": ev.message,
            "status": st,
            "acknowledged_by": ev.acknowledged_by,
            "acknowledged_at": ev.acknowledged_at.isoformat() if ev.acknowledged_at else None,
            "resolved_at": ev.acknowledged_at.isoformat() if ev.acknowledged_at else None,
            "comment": f"Actor: {ev.actor}",
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        })

    combined = sorted(items + sec_items, key=lambda x: x.get("created_at") or "", reverse=True)[:limit]
    return {
        "incidents": combined,
        "count": len(combined),
        "active_count": sum(1 for x in combined if x["status"] == "active"),
    }


@router.post("/incidents", status_code=status.HTTP_201_CREATED)
async def create_incident(
    body: IncidentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("sensors:write")),
):
    if body.severity not in VALID_SEVERITIES:
        raise HTTPException(status_code=400, detail=f"Invalid severity '{body.severity}'")
    sensor = (await db.execute(
        select(Sensor).where((Sensor.id == body.sensor_id) | (Sensor.identifier == body.sensor_id))
    )).scalar_one_or_none()
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    alert = Alert(
        sensor_id=sensor.id,
        metric_type=body.metric_type.strip(),
        severity=body.severity,
        reading_value=body.reading_value,
        threshold_value=body.threshold_value,
        message=body.message.strip(),
        status="active",
        comment=body.comment,
    )
    db.add(alert)
    await db.flush()
    await _write_audit(db, current_user, request, "alert.incident.create", "alert", alert.id, {"sensor": sensor.name, "severity": alert.severity})
    await db.commit()
    return _serialize_incident(alert, {sensor.id: sensor})


@router.patch("/incidents/{alert_id}")
async def update_incident(
    alert_id: str,
    body: IncidentUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("sensors:write")),
):
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Incident not found")
    now = datetime.now(timezone.utc)
    if body.status is not None:
        if body.status not in VALID_INCIDENT_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status '{body.status}'")
        alert.status = body.status
        if body.status == "acknowledged":
            alert.acknowledged_by = current_user.id
            alert.acknowledged_at = now
        elif body.status == "resolved":
            alert.resolved_at = now
            if not alert.acknowledged_at:
                alert.acknowledged_by = current_user.id
                alert.acknowledged_at = now
    if body.severity is not None:
        if body.severity not in VALID_SEVERITIES:
            raise HTTPException(status_code=400, detail=f"Invalid severity '{body.severity}'")
        alert.severity = body.severity
    if body.message is not None:
        alert.message = body.message.strip()
    if body.comment is not None:
        alert.comment = body.comment

    await _write_audit(db, current_user, request, "alert.incident.update", "alert", alert.id, {"status": alert.status})
    await db.commit()
    sensor = (await db.execute(select(Sensor).where(Sensor.id == alert.sensor_id))).scalar_one_or_none()
    return _serialize_incident(alert, {sensor.id: sensor} if sensor else {})


@router.delete("/incidents/{alert_id}")
async def delete_incident(
    alert_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("sensors:write")),
):
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Incident not found")
    await db.delete(alert)
    await _write_audit(db, current_user, request, "alert.incident.delete", "alert", alert_id, {})
    await db.commit()
    return {"deleted": True, "id": alert_id}


# ── Executive & SLA Reporting (Summary + Export CSV / JSON / Printable HTML) ─

async def _build_report_payload(db: AsyncSession) -> Dict[str, Any]:
    sensors = (await db.execute(select(Sensor).order_by(Sensor.name))).scalars().all()
    racks = (await db.execute(select(Rack).options(selectinload(Rack.devices)).order_by(Rack.name))).scalars().all()
    cables = (await db.execute(select(RackCable))).scalars().all()
    sec_devs = (await db.execute(select(SecurityDevice))).scalars().all()
    alerts = (await db.execute(select(Alert).order_by(Alert.created_at.desc()).limit(200))).scalars().all()
    rules = await _ensure_default_rules(db)

    temps = [s.current_temperature for s in sensors if s.current_temperature is not None]
    hums = [s.current_humidity for s in sensors if s.current_humidity is not None]

    total_u = sum(r.u_height for r in racks)
    used_u = sum(sum(d.u_height for d in r.devices) for r in racks)
    total_power_w = round(sum(sum(float(d.power_w or 0.0) for d in r.devices) for r in racks), 1)
    total_rack_devices = sum(len(r.devices) for r in racks)

    sensor_map = {s.id: s for s in sensors}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "sensor_count": len(sensors),
            "avg_temp_c": round(sum(temps) / len(temps), 2) if temps else None,
            "max_temp_c": round(max(temps), 2) if temps else None,
            "min_temp_c": round(min(temps), 2) if temps else None,
            "avg_humidity_pct": round(sum(hums) / len(hums), 2) if hums else None,
            "sensors": [
                {
                    "name": s.name,
                    "identifier": s.identifier,
                    "type": s.sensor_type,
                    "temp_c": s.current_temperature,
                    "humidity_pct": s.current_humidity,
                    "status": s.status,
                }
                for s in sensors
            ],
        },
        "infrastructure": {
            "rack_count": len(racks),
            "mounted_devices": total_rack_devices,
            "structured_cables": len(cables),
            "u_used": used_u,
            "u_total": total_u,
            "u_utilization_pct": round((used_u / total_u) * 100.0, 1) if total_u else 0.0,
            "total_power_w": total_power_w,
        },
        "security": {
            "device_count": len(sec_devs),
            "cctv_count": sum(1 for d in sec_devs if d.device_kind == "cctv"),
            "door_access_count": sum(1 for d in sec_devs if d.device_kind in ("door_access", "fingerprint")),
            "sensor_count": sum(1 for d in sec_devs if d.device_kind in ("motion", "contact")),
            "active_security_alerts": sum(1 for d in sec_devs if d.alert_active),
        },
        "incidents": {
            "rule_count": len(rules),
            "enabled_rules": sum(1 for r in rules if r.enabled),
            "total": len(alerts),
            "active": sum(1 for a in alerts if a.status == "active"),
            "acknowledged": sum(1 for a in alerts if a.status == "acknowledged"),
            "resolved": sum(1 for a in alerts if a.status == "resolved"),
            "items": [_serialize_incident(a, sensor_map) for a in alerts[:50]],
        },
    }


@router.get("/reports/summary")
async def get_reports_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("sensors:read")),
):
    return await _build_report_payload(db)


@router.get("/reports/export")
async def export_dcim_report(
    format: str = Query(default="csv", pattern="^(csv|json|html)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("sensors:read")),
):
    """Export unified DCIM Operations & Incident Report as CSV, JSON, or printable HTML (Save as PDF)."""
    report = await _build_report_payload(db)
    date_tag = datetime.now(timezone.utc).strftime("%Y%m%d")

    if format == "json":
        return Response(
            content=json.dumps(report, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="dcim_report_{date_tag}.json"'},
        )

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Section", "Name / Metric", "Value / Reading", "Threshold / Status", "Timestamp / Notes"])
        env = report["environment"]
        writer.writerow(["Environment", "Sensors", env["sensor_count"], f"Avg Temp: {env['avg_temp_c']} C", f"Avg RH: {env['avg_humidity_pct']}%"])
        inf = report["infrastructure"]
        writer.writerow(["Infrastructure", "Racks", inf["rack_count"], f"U Used: {inf['u_used']}/{inf['u_total']} ({inf['u_utilization_pct']}%)", f"Power: {inf['total_power_w']} W · Cables: {inf['structured_cables']}"])
        sec = report["security"]
        writer.writerow(["Security", "Devices", sec["device_count"], f"CCTV: {sec['cctv_count']} · Doors: {sec['door_access_count']}", f"Active Alerts: {sec['active_security_alerts']}"])
        for s in env["sensors"]:
            writer.writerow(["Sensor", s["name"], f"{s['temp_c']} C / {s['humidity_pct']}%", s["status"], s["identifier"]])
        for inc in report["incidents"]["items"]:
            writer.writerow(["Incident", inc["sensor_name"], f"{inc['reading_value']} ({inc['metric_type']})", f"{inc['severity']} / {inc['status']}", f"{inc['created_at']} — {inc['message']}"])
        return Response(
            content=buf.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="dcim_report_{date_tag}.csv"'},
        )

    # Printable HTML report (zero external assets, print-ready for PDF)
    env = report["environment"]
    inf = report["infrastructure"]
    sec = report["security"]
    inc = report["incidents"]
    inc_rows = "".join(
        f"<tr><td>{html.escape(str(i['created_at'] or ''))}</td><td>{html.escape(i['sensor_name'])}</td>"
        f"<td>{html.escape(i['severity'].upper())}</td><td>{html.escape(i['status'])}</td>"
        f"<td>{html.escape(i['message'])}</td></tr>"
        for i in inc["items"]
    ) or '<tr><td colspan="5" style="text-align:center;color:#64748b;">No incidents recorded.</td></tr>'

    html_doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Server_Monits DCIM Report ({date_tag})</title>
<style>
  body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; color: #0f172a; margin: 28px; }}
  h1 {{ color: #0284c7; margin-bottom: 4px; }}
  .meta {{ color: #64748b; font-size: 13px; margin-bottom: 20px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 22px; }}
  .kpi {{ border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px; background: #f8fafc; }}
  .kpi b {{ font-size: 20px; display: block; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }}
  th, td {{ border: 1px solid #cbd5e1; padding: 7px 10px; text-align: left; }}
  th {{ background: #e2e8f0; }}
  @media print {{ button {{ display: none; }} }}
</style></head><body>
  <button onclick="window.print()" style="float:right;padding:8px 14px;cursor:pointer;">🖨️ Print / Save PDF</button>
  <h1>Server_Monits — DCIM Executive &amp; Incident Report</h1>
  <div class="meta">Generated: {html.escape(report['generated_at'])}</div>
  <div class="kpis">
    <div class="kpi">Sensors / Avg Temp<b>{env['sensor_count']} · {env['avg_temp_c'] or '—'} °C</b></div>
    <div class="kpi">Racks / U Utilization<b>{inf['rack_count']} · {inf['u_utilization_pct']}%</b></div>
    <div class="kpi">Total Rack Power<b>{inf['total_power_w']} W</b></div>
    <div class="kpi">Active Incidents / Security<b>{inc['active']} Env · {sec['active_security_alerts']} Sec</b></div>
  </div>
  <h2>Incident Timeline ({inc['total']})</h2>
  <table><thead><tr><th>Time</th><th>Source</th><th>Severity</th><th>Status</th><th>Message</th></tr></thead>
  <tbody>{inc_rows}</tbody></table>
</body></html>"""
    return Response(content=html_doc, media_type="text/html; charset=utf-8")
