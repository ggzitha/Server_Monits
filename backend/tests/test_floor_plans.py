import pytest
from sqlalchemy import select
from backend.app.core.security import hash_password
from backend.app.db.models.user import User, Role
from backend.app.db.models.system_config import SystemConfig
from backend.app.db.models.audit import AuditLog


@pytest.mark.asyncio
async def test_floor_plans_api_crud_and_permissions(client, db_session):
    # Fetch roles
    admin_role = (await db_session.execute(select(Role).where(Role.name == "Admin"))).scalar_one()
    viewer_role = (await db_session.execute(select(Role).where(Role.name == "Viewer"))).scalar_one()

    admin = User(username="admin_planner", email="adm_plan@test.com", password_hash=hash_password("adminpass"), is_active=True)
    admin.roles.append(admin_role)
    db_session.add(admin)

    viewer = User(username="viewer_planner", email="viw_plan@test.com", password_hash=hash_password("viewerpass"), is_active=True)
    viewer.roles.append(viewer_role)
    db_session.add(viewer)
    db_session.add(SystemConfig(key="is_initialized", value="true"))
    await db_session.commit()

    # 1. Anonymous access -> 401
    anon_res = await client.get("/api/v1/plans")
    assert anon_res.status_code == 401

    # 2. Login as Viewer
    login_viewer = await client.post("/api/v1/auth/login", json={"username": "viewer_planner", "password": "viewerpass"})
    assert login_viewer.status_code == 200
    viewer_csrf = login_viewer.json()["csrf_token"]

    # Viewer can read plans
    view_plans_res = await client.get("/api/v1/plans")
    assert view_plans_res.status_code == 200
    assert view_plans_res.json() == []

    # Viewer CANNOT create plans -> 403 Forbidden
    view_create = await client.post(
        "/api/v1/plans",
        headers={"X-CSRF-Token": viewer_csrf},
        json={"name": "Forbidden Plan", "site_name": "DC 1", "level_index": 0},
    )
    assert view_create.status_code == 403

    # 3. Login as Admin
    login_admin = await client.post("/api/v1/auth/login", json={"username": "admin_planner", "password": "adminpass"})
    assert login_admin.status_code == 200
    admin_csrf = login_admin.json()["csrf_token"]
    admin_headers = {"X-CSRF-Token": admin_csrf}

    # Admin creates a plan
    create_res = await client.post(
        "/api/v1/plans",
        headers=admin_headers,
        json={
            "name": "Main Server Hall",
            "site_name": "DC-Alpha",
            "level_index": 1,
            "grid_size_meters": 0.1,
            "scale_ratio": 1.0,
            "metadata_json": {"building": "North Wing"},
        },
    )
    assert create_res.status_code == 200
    plan_id = create_res.json()["id"]

    # Admin updates plan with rooms (walls) and placed objects (rack & sensor)
    update_res = await client.put(
        f"/api/v1/plans/{plan_id}",
        headers=admin_headers,
        json={
            "name": "Main Server Hall (Renamed)",
            "rooms": [
                {
                    "name": "Containment Room A",
                    "polygon_points": [[0.0, 0.0], [10.5, 0.0], [10.5, 8.2], [0.0, 8.2]],
                    "wall_height_m": 2.8,
                    "wall_thickness_m": 0.15,
                    "floor_color": "#0a0a0f",
                    "wall_color": "#00f0ff",
                }
            ],
            "objects": [
                {
                    "object_type": "rack",
                    "name": "Rack-A01",
                    "position_x": 2.5,
                    "position_y": 0.0,
                    "position_z": 3.0,
                    "rotation_x": 0.0,
                    "rotation_y": 90.0,
                    "rotation_z": 0.0,
                    "scale_x": 0.6,
                    "scale_y": 2.0,
                    "scale_z": 1.0,
                    "properties": {"capacity_u": 42, "status": "active"},
                },
                {
                    "object_type": "sensor",
                    "name": "Temp-Probe-01",
                    "position_x": 2.5,
                    "position_y": 1.2,
                    "position_z": 3.0,
                    "scale_x": 0.1,
                    "scale_y": 0.1,
                    "scale_z": 0.1,
                    "properties": {"metric_type": "temperature", "unit": "C"},
                },
            ],
        },
    )
    assert update_res.status_code == 200

    # Retrieve complete plan
    get_res = await client.get(f"/api/v1/plans/{plan_id}")
    assert get_res.status_code == 200
    plan_data = get_res.json()
    assert plan_data["name"] == "Main Server Hall (Renamed)"
    assert len(plan_data["rooms"]) == 1
    assert len(plan_data["objects"]) == 2
    assert plan_data["rooms"][0]["wall_height_m"] == 2.8
    assert plan_data["objects"][0]["name"] == "Rack-A01"
    assert plan_data["objects"][0]["position"]["x"] == 2.5

    # 4. JSON Export
    export_res = await client.post(f"/api/v1/plans/{plan_id}/export", headers=admin_headers)
    assert export_res.status_code == 200
    bundle = export_res.json()
    assert "version" in bundle
    assert bundle["plan"]["name"] == "Main Server Hall (Renamed)"
    assert len(bundle["rooms"]) == 1

    # 5. JSON Import
    bundle["plan"]["name"] = "Imported Server Hall"
    import_res = await client.post("/api/v1/plans/import", headers=admin_headers, json=bundle)
    assert import_res.status_code == 200
    imported_id = import_res.json()["id"]
    assert imported_id != plan_id

    # 6. Verify Audit Logs recorded
    audit_logs = (await db_session.execute(
        select(AuditLog).where(AuditLog.resource_type == "floor_plans")
    )).scalars().all()
    actions = [a.action for a in audit_logs]
    assert "PLAN_CREATE" in actions
    assert "PLAN_UPDATE" in actions
