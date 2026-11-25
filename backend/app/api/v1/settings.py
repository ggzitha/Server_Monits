import asyncio
import logging
from typing import Any, Dict, Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_db, require_permission
from backend.app.core.config import settings
from backend.app.core.security import encrypt_secret, decrypt_secret
from backend.app.db.models.system_config import SystemConfig
from backend.app.services.mqtt_service import mqtt_service

logger = logging.getLogger("server_monits.settings")

router = APIRouter(prefix="/settings", tags=["settings"])


class UpdateSettingsRequest(BaseModel):
    settings: Dict[str, str]


class TestGatewayRequest(BaseModel):
    url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None


class TestMqttRequest(BaseModel):
    host: str
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    tls: bool = False
    topic: str = "sensors/#"
    timeout: float = Field(default=5.0, ge=1.0, le=30.0)


@router.get("", dependencies=[Depends(require_permission("settings:read"))])
async def get_system_settings(db: AsyncSession = Depends(get_db)):
    """Fetch key-value system settings with sensitive values masked."""
    stmt = select(SystemConfig)
    res = await db.execute(stmt)
    rows = res.scalars().all()
    result = {}
    for row in rows:
        if row.key in ("mqtt_password", "go2rtc_password", "go2rtc_token"):
            result[f"{row.key}_set"] = bool(row.value)
            result[row.key] = "••••••••" if row.value else ""
        else:
            result[row.key] = row.value

    # Defaults from env if not set in DB
    if "go2rtc_url" not in result:
        result["go2rtc_url"] = settings.GO2RTC_API_URL or "http://frigate:1984"
    if "mqtt_host" not in result and settings.MQTT_HOST:
        result["mqtt_host"] = settings.MQTT_HOST
    if "mqtt_port" not in result:
        result["mqtt_port"] = str(settings.MQTT_PORT or 1883)
    if "mqtt_username" not in result and settings.MQTT_USERNAME:
        result["mqtt_username"] = settings.MQTT_USERNAME
    if "mqtt_tls" not in result:
        result["mqtt_tls"] = "true" if settings.MQTT_TLS else "false"
    if "mqtt_client_id" not in result and settings.MQTT_CLIENT_ID:
        result["mqtt_client_id"] = settings.MQTT_CLIENT_ID
    if "site_latitude" not in result:
        result["site_latitude"] = "-2.575550"
    if "site_longitude" not in result:
        result["site_longitude"] = "140.686402"

    return result


@router.put("", dependencies=[Depends(require_permission("settings:write"))])
async def update_system_settings(req: UpdateSettingsRequest, db: AsyncSession = Depends(get_db)):
    """Update system settings (telemetry retention, go2rtc, MQTT, theme, etc)."""
    mqtt_config_changed = False

    for key, val in req.settings.items():
        if key.startswith("mqtt_"):
            mqtt_config_changed = True

        # Handle sensitive encryption
        if key in ("mqtt_password", "go2rtc_password", "go2rtc_token"):
            if val and val != "••••••••":
                encrypted_val = encrypt_secret(val)
                stmt = select(SystemConfig).where(SystemConfig.key == key)
                res = await db.execute(stmt)
                cfg = res.scalar_one_or_none()
                if cfg:
                    cfg.value = encrypted_val
                else:
                    db.add(SystemConfig(key=key, value=encrypted_val))
            elif val == "":
                stmt = select(SystemConfig).where(SystemConfig.key == key)
                res = await db.execute(stmt)
                cfg = res.scalar_one_or_none()
                if cfg:
                    cfg.value = ""
            continue

        stmt = select(SystemConfig).where(SystemConfig.key == key)
        res = await db.execute(stmt)
        cfg = res.scalar_one_or_none()
        if cfg:
            cfg.value = str(val)
        else:
            db.add(SystemConfig(key=key, value=str(val)))

    await db.commit()

    # If MQTT settings were updated, reconfigure the running MQTT service
    if mqtt_config_changed:
        try:
            # Query current MQTT values from DB
            stmt = select(SystemConfig).where(SystemConfig.key.like("mqtt_%"))
            res = await db.execute(stmt)
            cfgs = {r.key: r.value for r in res.scalars().all()}

            m_host = cfgs.get("mqtt_host", settings.MQTT_HOST)
            m_port = int(cfgs.get("mqtt_port", settings.MQTT_PORT or 1883))
            m_user = cfgs.get("mqtt_username", settings.MQTT_USERNAME)
            m_pass_enc = cfgs.get("mqtt_password")
            m_tls = cfgs.get("mqtt_tls", "false").lower() in ("true", "1", "yes")
            m_client_id = cfgs.get("mqtt_client_id", settings.MQTT_CLIENT_ID)

            if m_host:
                mqtt_service.set_config(
                    host=m_host,
                    port=m_port,
                    username=m_user,
                    password_encrypted=m_pass_enc,
                    tls_enabled=m_tls,
                    client_id=m_client_id,
                )
                asyncio.create_task(mqtt_service.start())
        except Exception as e:
            logger.error(f"Failed to apply new MQTT settings to running service: {e}")

    return {"success": True, "message": "Settings updated"}


@router.post("/test-gateway", dependencies=[Depends(require_permission("settings:read"))])
async def test_gateway(req: TestGatewayRequest, db: AsyncSession = Depends(get_db)):
    """Test connection to Frigate / go2rtc REST API endpoint (supports Basic Auth & Bearer token)."""
    cfg_rows = (await db.execute(
        select(SystemConfig).where(SystemConfig.key.in_(("go2rtc_url", "go2rtc_username", "go2rtc_password", "go2rtc_token")))
    )).scalars().all()
    cfg_map = {r.key: r.value for r in cfg_rows}

    target_url = (req.url or cfg_map.get("go2rtc_url") or settings.GO2RTC_API_URL or "http://frigate:1984").strip().rstrip("/")
    if not target_url:
        return {"success": False, "message": "No Stream Gateway URL provided"}

    username = (req.username if req.username is not None else cfg_map.get("go2rtc_username") or "").strip()
    password = req.password
    if not password or password == "••••••••":
        raw_pw = cfg_map.get("go2rtc_password") or ""
        try:
            password = decrypt_secret(raw_pw) if raw_pw else ""
        except Exception:
            password = ""

    token = req.token
    if not token or token == "••••••••":
        raw_tok = cfg_map.get("go2rtc_token") or ""
        try:
            token = decrypt_secret(raw_tok) if raw_tok else ""
        except Exception:
            token = ""

    auth = httpx.BasicAuth(username, password) if (username or password) else None
    headers = {"Authorization": f"Bearer {token.strip()}"} if token and token.strip() else {}

    # Extract origin for Frigate 0.14+ JWT login (/api/login -> frigate_token cookie)
    from urllib.parse import urlparse
    parsed_u = urlparse(target_url)
    origin = f"{parsed_u.scheme}://{parsed_u.netloc}" if parsed_u.scheme and parsed_u.netloc else target_url

    # Build candidate stream list URLs: supports direct go2rtc (:1984) AND Frigate-proxied (/api/go2rtc/streams)
    low = target_url.lower()
    if low.endswith("/api/streams") or low.endswith("/api/go2rtc/streams"):
        candidates = [target_url]
    elif "/api/go2rtc/streams/" in low:
        candidates = [target_url, target_url.rsplit("/", 1)[0]]
    else:
        candidates = [f"{target_url}/api/go2rtc/streams", f"{target_url}/api/streams"]

    last_status = None
    last_body = ""
    last_url = candidates[0]
    frigate_logged_in = False
    try:
        async with httpx.AsyncClient(timeout=6.0, verify=False, follow_redirects=True, headers=headers) as client:
            # 1. Try Frigate 0.14–0.18 JWT login first when username/password are provided
            if username and password:
                try:
                    login_resp = await client.post(
                        f"{origin}/api/login",
                        json={"user": username, "password": password},
                    )
                    if login_resp.status_code == 200:
                        frigate_logged_in = True
                except Exception:
                    pass

            req_auth = None if frigate_logged_in else auth
            for api_url in candidates:
                last_url = api_url
                resp = await client.get(api_url, auth=req_auth)
                last_status = resp.status_code
                last_body = resp.text[:200]
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception:
                        continue
                    streams = list(data.keys()) if isinstance(data, dict) else []
                    mode_lbl = "Frigate JWT" if frigate_logged_in else ("Basic Auth" if req_auth else "Open")
                    return {
                        "success": True,
                        "message": f"Successfully connected to go2rtc API ({api_url}) via {mode_lbl}. {len(streams)} active stream(s) found.",
                        "streams": streams,
                    }
                if resp.status_code == 401:
                    return {
                        "success": False,
                        "message": "Gateway responded with HTTP status 401 (Authorization Required). Check your Frigate username & password.",
                    }
        return {
            "success": False,
            "message": f"Gateway responded with HTTP status {last_status}: {last_body}",
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Could not connect to go2rtc at {last_url}: {str(e)}",
        }


@router.post("/test-mqtt", dependencies=[Depends(require_permission("settings:read"))])
async def test_mqtt(req: TestMqttRequest, db: AsyncSession = Depends(get_db)):
    """Test connection to an external Mosquitto broker and listen for sample message on topic."""
    password = req.password
    # If password is masked or empty, try reading decrypted password from DB
    if not password or password == "••••••••":
        stmt = select(SystemConfig).where(SystemConfig.key == "mqtt_password")
        res = await db.execute(stmt)
        cfg = res.scalar_one_or_none()
        if cfg and cfg.value:
            try:
                password = decrypt_secret(cfg.value)
            except Exception:
                password = ""
        else:
            password = settings.MQTT_PASSWORD or ""

    result = await mqtt_service.test_connection(
        host=req.host,
        port=req.port,
        username=req.username or "",
        password=password or "",
        tls=req.tls,
        topic=req.topic,
        timeout=req.timeout,
    )
    return result


@router.get("/mqtt-status", dependencies=[Depends(require_permission("settings:read"))])
async def get_mqtt_status():
    """Get live MQTT connection status and statistics."""
    return {
        "status": mqtt_service.connection_status,
        "is_connected": mqtt_service.is_connected,
        "last_error": mqtt_service.last_error,
        "last_seen_message_at": mqtt_service.last_seen_message_at,
    }
