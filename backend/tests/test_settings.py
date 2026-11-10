import pytest
from sqlalchemy import select
from backend.app.core.security import hash_password
from backend.app.db.models.user import User, Role
from backend.app.db.models.system_config import SystemConfig


@pytest.mark.asyncio
async def test_settings_gateway_and_mqtt(client, db_session):
    roles = (await db_session.execute(select(Role))).scalars().all()
    role_map = {r.name: r for r in roles}

    # Create admin user
    user = User(
        username="admin_settings",
        email="admin_settings@example.com",
        password_hash=hash_password("SecretSettingsPass123!"),
        is_active=True,
    )
    user.roles.append(role_map["Admin"])
    db_session.add(user)
    db_session.add(SystemConfig(key="is_initialized", value="true"))
    await db_session.commit()

    # Login to get session cookie & csrf token
    login_res = await client.post("/api/v1/auth/login", json={
        "username": "admin_settings",
        "password": "SecretSettingsPass123!",
    })
    assert login_res.status_code == 200
    csrf_token = login_res.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_token}

    # 1. Update settings with MQTT and go2rtc
    res = await client.put("/api/v1/settings", headers=headers, json={
        "settings": {
            "go2rtc_url": "http://127.0.0.1:1984",
            "mqtt_host": "127.0.0.1",
            "mqtt_port": "1883",
            "mqtt_username": "reader",
            "mqtt_password": "supersecretpassword",
        }
    })
    assert res.status_code == 200

    # 2. Get settings: check password masking
    res_get = await client.get("/api/v1/settings", headers=headers)
    assert res_get.status_code == 200
    data = res_get.json()
    assert data["go2rtc_url"] == "http://127.0.0.1:1984"
    assert data["mqtt_host"] == "127.0.0.1"
    assert data["mqtt_password_set"] is True
    assert data["mqtt_password"] == "••••••••"

    # 3. Test MQTT status endpoint
    res_status = await client.get("/api/v1/settings/mqtt-status", headers=headers)
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert "status" in status_data
    assert "is_connected" in status_data

    # 4. Test Gateway endpoint (with dummy unreachable URL)
    res_gw = await client.post("/api/v1/settings/test-gateway", headers=headers, json={"url": "http://127.0.0.1:9999"})
    assert res_gw.status_code == 200
    gw_data = res_gw.json()
    assert gw_data["success"] is False
    assert "Could not connect to go2rtc" in gw_data["message"]
