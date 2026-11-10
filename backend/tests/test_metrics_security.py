import pytest
from sqlalchemy import select
from backend.app.core.security import hash_password
from backend.app.db.models.user import User, Role
from backend.app.db.models.system_config import SystemConfig


@pytest.mark.asyncio
async def test_metrics_protected_access(client, db_session):
    # Seed Admin and Viewer
    admin_role = (await db_session.execute(select(Role).where(Role.name == "Admin"))).scalar_one()
    viewer_role = (await db_session.execute(select(Role).where(Role.name == "Viewer"))).scalar_one()

    admin = User(username="admin_metrics", email="adm@m.com", password_hash=hash_password("adminpass"), is_active=True)
    admin.roles.append(admin_role)
    db_session.add(admin)

    viewer = User(username="viewer_metrics", email="viw@m.com", password_hash=hash_password("viewpass"), is_active=True)
    viewer.roles.append(viewer_role)
    db_session.add(viewer)
    db_session.add(SystemConfig(key="is_initialized", value="true"))
    await db_session.commit()

    # 1. Unauthenticated request without headers -> 403
    res_raw = await client.get("/metrics")
    assert res_raw.status_code == 403

    # 2. Unauthenticated request spoofing internal IP headers (127.0.0.1, 10.x, etc.) -> MUST BE 403 (Never trust IP)
    res_spoof_loopback = await client.get("/metrics", headers={"X-Forwarded-For": "127.0.0.1"})
    assert res_spoof_loopback.status_code == 403

    res_spoof_lan = await client.get("/metrics", headers={"X-Forwarded-For": "192.168.1.100"})
    assert res_spoof_lan.status_code == 403

    # 3. Authenticated as Viewer -> 403 Forbidden
    await client.post("/api/v1/auth/login", json={"username": "viewer_metrics", "password": "viewpass"})
    viewer_res = await client.get("/metrics")
    assert viewer_res.status_code == 403

    # 4. Authenticated as Admin -> 200 OK
    await client.post("/api/v1/auth/login", json={"username": "admin_metrics", "password": "adminpass"})
    admin_res = await client.get("/metrics")
    assert admin_res.status_code == 200
    assert "server_monits_up 1" in admin_res.text
