import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.sensor import Sensor
from backend.app.db.models.telemetry import TelemetryReading
from backend.app.db.models.alert import Alert
from backend.app.services.notifier import notifier

logger = logging.getLogger("server_monits.ingestion")


def parse_telemetry_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and normalize sensor fields from incoming JSON payloads."""
    # Identifier (MAC, serial, id, sensor_id)
    ident = (
        payload.get("sensor_id")
        or payload.get("identifier")
        or payload.get("id")
        or payload.get("mac")
        or payload.get("device_id")
    )
    if not ident:
        raise ValueError("Missing sensor identifier in payload")

    # Temperature
    raw_temp = payload.get("temperature") or payload.get("temp")
    temp_c = None
    if raw_temp is not None:
        temp_val = float(raw_temp)
        unit = str(payload.get("unit", payload.get("temp_unit", "C"))).upper()
        if "F" in unit:
            temp_c = round((temp_val - 32.0) * 5.0 / 9.0, 2)
        else:
            temp_c = round(temp_val, 2)

    # Humidity
    raw_hum = payload.get("humidity") or payload.get("hum") or payload.get("rh")
    hum_pct = round(float(raw_hum), 2) if raw_hum is not None else None

    # Battery & RSSI
    battery = payload.get("battery") or payload.get("battery_level") or payload.get("batt")
    batt_pct = float(battery) if battery is not None else None

    # Timestamp
    now = datetime.now(timezone.utc)
    raw_ts = payload.get("timestamp") or payload.get("time")
    ts = now
    if raw_ts:
        if isinstance(raw_ts, (int, float)):
            # Unix epoch
            if raw_ts > 1e11:  # milliseconds
                raw_ts /= 1000.0
            ts = datetime.fromtimestamp(raw_ts, timezone.utc)
        elif isinstance(raw_ts, str):
            try:
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            except Exception:
                ts = now

    return {
        "identifier": str(ident).strip(),
        "temperature": temp_c,
        "humidity": hum_pct,
        "battery_level": batt_pct,
        "timestamp": ts,
        "raw_data": payload,
    }


def evaluate_sensor_status(sensor: Sensor, temp: Optional[float], hum: Optional[float]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Check readings against configured warning and critical thresholds."""
    status = "online"
    alert_info = None

    if temp is not None:
        if sensor.temp_max_critical is not None and temp >= sensor.temp_max_critical:
            status = "critical"
            alert_info = {
                "metric": "temperature",
                "severity": "critical",
                "val": temp,
                "threshold": sensor.temp_max_critical,
                "msg": f"Critical High Temperature: {temp}°C exceeds max {sensor.temp_max_critical}°C",
            }
        elif sensor.temp_min_critical is not None and temp <= sensor.temp_min_critical:
            status = "critical"
            alert_info = {
                "metric": "temperature",
                "severity": "critical",
                "val": temp,
                "threshold": sensor.temp_min_critical,
                "msg": f"Critical Low Temperature: {temp}°C below min {sensor.temp_min_critical}°C",
            }
        elif sensor.temp_max_warning is not None and temp >= sensor.temp_max_warning:
            status = "warning"
            alert_info = {
                "metric": "temperature",
                "severity": "warning",
                "val": temp,
                "threshold": sensor.temp_max_warning,
                "msg": f"Warning High Temperature: {temp}°C exceeds warning {sensor.temp_max_warning}°C",
            }
        elif sensor.temp_min_warning is not None and temp <= sensor.temp_min_warning:
            status = "warning"
            alert_info = {
                "metric": "temperature",
                "severity": "warning",
                "val": temp,
                "threshold": sensor.temp_min_warning,
                "msg": f"Warning Low Temperature: {temp}°C below warning {sensor.temp_min_warning}°C",
            }

    if status != "critical" and hum is not None:
        if sensor.humidity_max_critical is not None and hum >= sensor.humidity_max_critical:
            status = "critical"
            alert_info = {
                "metric": "humidity",
                "severity": "critical",
                "val": hum,
                "threshold": sensor.humidity_max_critical,
                "msg": f"Critical High Humidity: {hum}%RH exceeds {sensor.humidity_max_critical}%RH",
            }
        elif sensor.humidity_min_critical is not None and hum <= sensor.humidity_min_critical:
            status = "critical"
            alert_info = {
                "metric": "humidity",
                "severity": "critical",
                "val": hum,
                "threshold": sensor.humidity_min_critical,
                "msg": f"Critical Low Humidity: {hum}%RH below {sensor.humidity_min_critical}%RH",
            }
        elif sensor.humidity_max_warning is not None and hum >= sensor.humidity_max_warning and status == "online":
            status = "warning"
            alert_info = {
                "metric": "humidity",
                "severity": "warning",
                "val": hum,
                "threshold": sensor.humidity_max_warning,
                "msg": f"Warning High Humidity: {hum}%RH exceeds {sensor.humidity_max_warning}%RH",
            }

    return status, alert_info


async def process_telemetry_reading(
    db: AsyncSession,
    payload: Dict[str, Any],
    data_source_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Ingest, store, evaluate thresholds, and broadcast telemetry update."""
    parsed = parse_telemetry_payload(payload)
    identifier = parsed["identifier"]
    temp = parsed["temperature"]
    hum = parsed["humidity"]
    batt = parsed["battery_level"]
    ts = parsed["timestamp"]

    # 1. Lookup or Auto-Discover Sensor
    stmt = select(Sensor).where(Sensor.identifier == identifier)
    res = await db.execute(stmt)
    sensor = res.scalar_one_or_none()

    if not sensor:
        sensor = Sensor(
            identifier=identifier,
            name=f"Discovered Sensor {identifier[:8]}",
            sensor_type="thermohygrometer",
            is_discovered=True,
            data_source_id=data_source_id,
            status="online",
        )
        db.add(sensor)
        await db.flush()
        logger.info(f"Auto-discovered new sensor: {identifier}")

    # 2. Evaluate Status & Alerts
    new_status, alert_data = evaluate_sensor_status(sensor, temp, hum)
    sensor.current_temperature = temp
    sensor.current_humidity = hum
    if batt is not None:
        sensor.battery_level = batt
    sensor.last_seen_at = ts
    sensor.status = new_status

    # 3. Create or Resolve Alerts
    if alert_data:
        # Check if active alert already exists for this sensor and metric
        active_stmt = select(Alert).where(
            Alert.sensor_id == sensor.id,
            Alert.metric_type == alert_data["metric"],
            Alert.status == "active",
        )
        existing_alert = (await db.execute(active_stmt)).scalar_one_or_none()
        if not existing_alert:
            new_alert = Alert(
                sensor_id=sensor.id,
                metric_type=alert_data["metric"],
                severity=alert_data["severity"],
                reading_value=alert_data["val"],
                threshold_value=alert_data["threshold"],
                message=alert_data["msg"],
                status="active",
            )
            db.add(new_alert)
            await db.flush()
            # Broadcast immediate alert
            await notifier.broadcast_alert({
                "alert_id": new_alert.id,
                "sensor_id": sensor.id,
                "sensor_name": sensor.name,
                "severity": new_alert.severity,
                "message": new_alert.message,
                "reading": new_alert.reading_value,
            })
    else:
        # Resolve active alerts if status returned to normal
        resolve_stmt = select(Alert).where(
            Alert.sensor_id == sensor.id,
            Alert.status == "active",
        )
        active_alerts = (await db.execute(resolve_stmt)).scalars().all()
        for a in active_alerts:
            a.status = "resolved"
            a.resolved_at = datetime.now(timezone.utc)

    # 4. Insert Telemetry Reading (BigInt PK, Time-Series)
    reading = TelemetryReading(
        sensor_id=sensor.id,
        timestamp=ts,
        temperature=temp,
        humidity=hum,
        raw_data=parsed["raw_data"],
    )
    db.add(reading)
    await db.commit()

    # 5. Broadcast Telemetry Update via WebSocket (Throttled to 1s)
    await notifier.broadcast_telemetry(sensor.id, {
        "sensor_name": sensor.name,
        "object_id": sensor.object_id,
        "temperature": temp,
        "humidity": hum,
        "battery_level": batt,
        "status": new_status,
    })

    return {
        "sensor_id": sensor.id,
        "identifier": sensor.identifier,
        "temperature": temp,
        "humidity": hum,
        "status": new_status,
        "is_discovered": sensor.is_discovered,
    }

