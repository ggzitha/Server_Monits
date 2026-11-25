"""
test_security_devices.py - Phase 6 unit & integration tests:
- SecurityDevice CRUD (CCTV cameras with 3D FOV cones, biometric fingerprint/door access, motion/contact).
- Live offline CCTV snapshot SVG endpoint (/api/v1/security/cameras/{id}/snapshot).
- Security actions (lock/unlock, grant/deny access, trigger/clear motion, toggle 3D cone, alert ack) + SecurityEvent timeline.
- RBAC enforcement (Security Officer can read/view snapshots, cannot mutate; Admin can mutate) + AuditLog recording.
"""
import pytest
from sqlalchemy import select
from backend.app.api.v1.security import resolve_frigate_go2rtc_urls
from backend.app.core.security import hash_password


def test_resolve_frigate_go2rtc_urls():
    res = resolve_frigate_go2rtc_urls(
        "https://inskal-cctv.balai5.my.id/api/go2rtc/streams/inskal_main_lobby"
    )
    assert "https://inskal-cctv.balai5.my.id/api/go2rtc/frame.jpeg?src=inskal_main_lobby" in res["snapshot_candidates"]
    assert "https://inskal-cctv.balai5.my.id/api/inskal_main_lobby/latest.jpg" in res["snapshot_candidates"]
    assert "https://inskal-cctv.balai5.my.id/api/go2rtc/stream.mjpeg?src=inskal_main_lobby" in res["stream_candidates"]
    assert "https://inskal-cctv.balai5.my.id/api/inskal_main_lobby" in res["stream_candidates"]

    res_rtsp = resolve_frigate_go2rtc_urls("rtsp://192.168.88.66:8554/inskal_main_lobby")
    assert res_rtsp["rtsp_candidates"] == ["rtsp://192.168.88.66:8554/inskal_main_lobby"]
from backend.app.db.models.audit import AuditLog
from backend.app.db.models.system_config import SystemConfig
from backend.app.db.models.user import Role, User


@pytest.mark.asyncio
async def test_security_devices_crud_actions_snapshots_and_rbac(client, db_session):
    admin_role = (await db_session.execute(select(Role).where(Role.name == "Admin"))).scalar_one()
    sec_role = (await db_session.execute(select(Role).where(Role.name == "Security Officer"))).scalar_one()

    admin = User(username="sec_admin", email="sec_admin@test.com", password_hash=hash_password("adminpass123"), is_active=True)
    admin.roles.append(admin_role)
    officer = User(username="sec_officer", email="sec_officer@test.com", password_hash=hash_password("officerpass123"), is_active=True)
    officer.roles.append(sec_role)
    db_session.add_all([admin, officer, SystemConfig(key="is_initialized", value="true")])
    await db_session.commit()

    # Login as Admin
    login_a = await client.post("/api/v1/auth/login", json={"username": "sec_admin", "password": "adminpass123"})
    assert login_a.status_code == 200
    adm_headers = {"X-CSRF-Token": login_a.json()["csrf_token"]}

    # 1. List devices (auto-seeds default CCTV, biometric door, motion, contact)
    res_list = await client.get("/api/v1/security/devices", headers=adm_headers)
    assert res_list.status_code == 200
    data = res_list.json()
    assert data["count"] >= 5
    kinds = {d["device_kind"] for d in data["devices"]}
    assert {"cctv", "fingerprint", "motion", "contact"}.issubset(kinds)

    # 2. Create a new CCTV camera with 3D FOV cone
    res_create = await client.post(
        "/api/v1/security/devices",
        headers=adm_headers,
        json={
            "name": "CCTV Cold Aisle North",
            "device_kind": "cctv",
            "floor_id": "ground",
            "pos_x": 6.5,
            "pos_z": 1.2,
            "pos_y": 3.0,
            "rotation": 210.0,
            "fov_deg": 90.0,
            "reach_m": 8.5,
            "cone_enabled": True,
        },
    )
    assert res_create.status_code == 201
    cam = res_create.json()
    assert cam["device_kind"] == "cctv"
    assert cam["cone_enabled"] is True

    # 3. Verify live offline CCTV SVG snapshot endpoint
    snap_res = await client.get(f"/api/v1/security/cameras/{cam['id']}/snapshot", headers=adm_headers)
    assert snap_res.status_code == 200
    assert "image/svg+xml" in snap_res.headers["content-type"]
    assert "CCTV Cold Aisle North" in snap_res.text

    # 4. Trigger camera alert & verify active_alerts count + event log + acknowledge
    act_alert = await client.post(
        f"/api/v1/security/devices/{cam['id']}/action",
        headers=adm_headers,
        json={"action": "trigger_alert", "message": "Perimeter breach detected"},
    )
    assert act_alert.status_code == 200
    assert act_alert.json()["device"]["alert_active"] is True
    assert act_alert.json()["event"]["severity"] == "critical"

    # Toggle 3D cone off
    act_cone = await client.post(
        f"/api/v1/security/devices/{cam['id']}/action",
        headers=adm_headers,
        json={"action": "toggle_cone"},
    )
    assert act_cone.status_code == 200
    assert act_cone.json()["device"]["cone_enabled"] is False

    # Acknowledge alert
    act_ack = await client.post(
        f"/api/v1/security/devices/{cam['id']}/action",
        headers=adm_headers,
        json={"action": "ack_alert"},
    )
    assert act_ack.status_code == 200
    assert act_ack.json()["device"]["alert_active"] is False

    # 5. Test Biometric Door Access (deny -> alert, grant -> unlocked + clear)
    door = next(d for d in data["devices"] if d["device_kind"] == "fingerprint")
    deny_res = await client.post(
        f"/api/v1/security/devices/{door['id']}/action",
        headers=adm_headers,
        json={"action": "deny_access", "actor": "Unknown Badge #99"},
    )
    assert deny_res.status_code == 200
    assert deny_res.json()["device"]["alert_active"] is True

    grant_res = await client.post(
        f"/api/v1/security/devices/{door['id']}/action",
        headers=adm_headers,
        json={"action": "grant_access", "actor": "Lead Engineer"},
    )
    assert grant_res.status_code == 200
    assert grant_res.json()["device"]["state"] == "unlocked"
    assert grant_res.json()["device"]["alert_active"] is False

    # 6. Verify events timeline & AuditLog
    ev_res = await client.get("/api/v1/security/events", headers=adm_headers)
    assert ev_res.status_code == 200
    assert ev_res.json()["count"] >= 5

    audits = (await db_session.execute(select(AuditLog).where(AuditLog.action.like("security.%")))).scalars().all()
    assert len(audits) >= 5

    # 7. RBAC: Security Officer can GET devices/events/snapshots (200), CANNOT POST/DELETE (403)
    login_o = await client.post("/api/v1/auth/login", json={"username": "sec_officer", "password": "officerpass123"})
    assert login_o.status_code == 200
    off_headers = {"X-CSRF-Token": login_o.json()["csrf_token"]}

    assert (await client.get("/api/v1/security/devices", headers=off_headers)).status_code == 200
    assert (await client.get(f"/api/v1/security/cameras/{cam['id']}/snapshot", headers=off_headers)).status_code == 200
    assert (await client.post("/api/v1/security/devices", headers=off_headers, json={"name": "Blocked", "device_kind": "cctv"})).status_code == 403
    assert (await client.delete(f"/api/v1/security/devices/{cam['id']}", headers=off_headers)).status_code == 403
