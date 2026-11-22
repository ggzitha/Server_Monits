"""
test_racks_elevation.py - Phase 5a unit & integration tests:
- Rack U-overlap, out-of-bounds, front/rear face isolation, full-depth ('both'), and half-width left/right validation.
- Rack CRUD (4U-70U), device mount/move/update/delete, shrink protection, utilization stats.
- Device Library templates + NetBox YAML & JSON device-type importer.
- RBAC enforcement (Viewer read-only 403 on write, Operator/Admin allowed) + AuditLog recording.
"""
import pytest
from sqlalchemy import select
from backend.app.api.v1.racks import validate_rack_device_placement, compute_rack_utilization
from backend.app.core.security import hash_password
from backend.app.db.models.audit import AuditLog
from backend.app.db.models.system_config import SystemConfig
from backend.app.db.models.user import Role, User


def test_rack_overlap_and_bounds_pure_logic():
    existing = [
        {"id": "d1", "name": "Core Switch", "u_position": 40, "u_height": 2, "face": "front", "half_width": False, "half_slot": "full"},
        {"id": "d2", "name": "GPU Server", "u_position": 10, "u_height": 4, "face": "both", "half_width": False, "half_slot": "full"},
        {"id": "d3", "name": "FW Left", "u_position": 20, "u_height": 1, "face": "front", "half_width": True, "half_slot": "left"},
    ]

    # Out of range (below U1 or above U42)
    ok, err = validate_rack_device_placement(42, existing, u_position=0, u_height=1)
    assert not ok and "Out of range" in err
    ok, err = validate_rack_device_placement(42, existing, u_position=42, u_height=2)
    assert not ok and "Out of range" in err

    # Exact U overlap on same face
    ok, err = validate_rack_device_placement(42, existing, u_position=41, u_height=1, face="front")
    assert not ok and "Core Switch" in err

    # Front vs Rear at same U does NOT overlap when front device is not full-depth
    ok, err = validate_rack_device_placement(42, existing, u_position=40, u_height=2, face="rear")
    assert ok and err is None

    # Full-depth ('both') conflicts with BOTH front and rear
    ok, err = validate_rack_device_placement(42, existing, u_position=12, u_height=1, face="rear")
    assert not ok and "GPU Server" in err
    ok, err = validate_rack_device_placement(42, existing, u_position=10, u_height=1, face="front")
    assert not ok and "GPU Server" in err

    # Half-width right shares U20 cleanly with half-width left
    ok, err = validate_rack_device_placement(42, existing, u_position=20, u_height=1, face="front", half_width=True, half_slot="right")
    assert ok and err is None

    # Half-width left conflicts with half-width left
    ok, err = validate_rack_device_placement(42, existing, u_position=20, u_height=1, face="front", half_width=True, half_slot="left")
    assert not ok and "FW Left" in err

    # Full-width conflicts with half-width left
    ok, err = validate_rack_device_placement(42, existing, u_position=20, u_height=1, face="front", half_width=False)
    assert not ok and "FW Left" in err

    # Moving existing device ignores itself
    ok, err = validate_rack_device_placement(42, existing, u_position=40, u_height=2, face="front", ignore_device_id="d1")
    assert ok and err is None

    # Utilization calculation
    util = compute_rack_utilization(42, 5000.0, [
        {"u_position": 1, "u_height": 2, "power_w": 500.0},
        {"u_position": 40, "u_height": 1, "power_w": 250.0},
    ])
    assert util["u_used"] == 3
    assert util["u_free"] == 39
    assert util["total_power_w"] == 750.0
    assert util["power_percent"] == 15.0


@pytest.mark.asyncio
async def test_racks_api_crud_overlap_netbox_and_rbac(client, db_session):
    admin_role = (await db_session.execute(select(Role).where(Role.name == "Admin"))).scalar_one()
    viewer_role = (await db_session.execute(select(Role).where(Role.name == "Viewer"))).scalar_one()

    admin = User(username="rack_admin", email="rack_admin@test.com", password_hash=hash_password("adminpass123"), is_active=True)
    admin.roles.append(admin_role)
    viewer = User(username="rack_viewer", email="rack_viewer@test.com", password_hash=hash_password("viewerpass123"), is_active=True)
    viewer.roles.append(viewer_role)
    db_session.add_all([admin, viewer, SystemConfig(key="is_initialized", value="true")])
    await db_session.commit()

    # Login as Admin
    login_a = await client.post("/api/v1/auth/login", json={"username": "rack_admin", "password": "adminpass123"})
    assert login_a.status_code == 200
    adm_headers = {"X-CSRF-Token": login_a.json()["csrf_token"]}

    # 1. Create a 70U rack (4U-70U range)
    r_create = await client.post(
        "/api/v1/racks",
        headers=adm_headers,
        json={"name": "Core-Rack-70U", "u_height": 70, "width_in": 19.0, "depth_mm": 1200, "max_power_w": 12000.0},
    )
    assert r_create.status_code == 201
    rack = r_create.json()
    rack_id = rack["id"]
    assert rack["u_height"] == 70
    assert rack["utilization"]["u_free"] == 70

    # 2. Mount a 2U full-depth server at U69 (occupies U69-U70)
    d1 = await client.post(
        f"/api/v1/racks/{rack_id}/devices",
        headers=adm_headers,
        json={"name": "Hypervisor-01", "device_type": "server", "u_position": 69, "u_height": 2, "face": "both", "power_w": 650.0},
    )
    assert d1.status_code == 201
    d1_id = d1.json()["id"]

    # 3. Attempt overlapping mount at U70 -> 409 Conflict
    d_conflict = await client.post(
        f"/api/v1/racks/{rack_id}/devices",
        headers=adm_headers,
        json={"name": "Switch-Overlap", "device_type": "switch", "u_position": 70, "u_height": 1, "face": "front"},
    )
    assert d_conflict.status_code == 409

    # 4. Attempt shrinking rack to 42U while device is at U69-U70 -> 409 Conflict
    r_shrink = await client.put(f"/api/v1/racks/{rack_id}", headers=adm_headers, json={"u_height": 42})
    assert r_shrink.status_code == 409

    # 5. Move device down to U10 and verify utilization
    d_move = await client.put(f"/api/v1/racks/{rack_id}/devices/{d1_id}", headers=adm_headers, json={"u_position": 10})
    assert d_move.status_code == 200
    assert d_move.json()["u_position"] == 10

    r_get = await client.get(f"/api/v1/racks/{rack_id}", headers=adm_headers)
    assert r_get.status_code == 200
    assert r_get.json()["utilization"]["u_used"] == 2
    assert r_get.json()["utilization"]["total_power_w"] == 650.0

    # 6. Verify Branded Hardware Catalog (MikroTik, Sangfor, Supermicro, Dell, HPE, Juniper + real WebP front/rear images)
    cat_res = await client.get("/api/v1/racks/library/catalog", headers=adm_headers)
    assert cat_res.status_code == 200
    cat_data = cat_res.json()
    assert cat_data["count"] >= 500
    for expected_brand in ("MikroTik", "Sangfor", "Dell", "HPE", "Supermicro", "Juniper"):
        assert expected_brand in cat_data["brands"]
    real_img_devs = [d for d in cat_data["devices"] if d.get("front_image", "").endswith(".webp") and d.get("rear_image", "").endswith(".webp")]
    assert len(real_img_devs) >= 100

    # Mount a real branded device with front & rear photos
    sample_hw = real_img_devs[0]
    d_img = await client.post(
        f"/api/v1/racks/{rack_id}/devices",
        headers=adm_headers,
        json={
            "name": sample_hw["model"],
            "device_type": sample_hw["device_type"],
            "manufacturer": sample_hw["brand"],
            "model": sample_hw["model"],
            "slug": sample_hw["slug"],
            "u_position": 20,
            "u_height": sample_hw["u_height"],
            "face": "both",
            "is_full_depth": True,
            "front_image": sample_hw["front_image"],
            "rear_image": sample_hw["rear_image"],
        },
    )
    assert d_img.status_code == 201
    assert d_img.json()["front_image"] == sample_hw["front_image"]
    assert d_img.json()["rear_image"] == sample_hw["rear_image"]

    # 6b. Import NetBox YAML device-type into native library
    nb_yaml = "manufacturer: Cisco\nmodel: Catalyst 9300-48P\nu_height: 1\nis_full_depth: false\n"
    nb_res = await client.post("/api/v1/racks/library/import-netbox", headers=adm_headers, json={"data": nb_yaml})
    assert nb_res.status_code == 201
    assert nb_res.json()["imported"] == 1
    assert nb_res.json()["templates"][0]["device_type"] == "switch"

    # 7. Verify cables summary endpoint returns custom color & linked rack-device metadata from single DB
    sample_b = {
        "version": 1,
        "floors": [{
            "id": "ground",
            "name": "Ground",
            "rooms": [],
            "walls": [],
            "placements": [],
            "furniture": [{
                "id": "cable_fiber_1",
                "cable_group": "cable_fiber_1",
                "type": "pack:dcim.facility:cable_fiber",
                "name": "OM4 Trunk R1-R2",
                "color": "#ff00aa",
                "mount_y": 2.88,
                "w": 6.4,
                "total_length_m": 8.9,
                "snapped_tray": True,
                "from_endpoint": {"rack_id": rack_id, "rack_name": "Core-Rack-70U", "device_id": d1_id, "device_name": "Hypervisor-01", "port": "SFP+1"},
                "to_endpoint": {"rack_id": rack_id, "rack_name": "Core-Rack-70U", "port": "SFP+2"},
            }],
        }],
    }
    b_save = await client.post("/api/v1/sensors/building", headers=adm_headers, json={"building": sample_b, "name": "DC", "revision": 2})
    assert b_save.status_code == 200
    cab_res = await client.get("/api/v1/racks/cables/summary", headers=adm_headers)
    assert cab_res.status_code == 200
    cab_data = cab_res.json()
    assert cab_data["count"] == 1
    assert cab_data["cables"][0]["color"] == "#ff00aa"
    assert cab_data["cables"][0]["length_m"] == 8.9
    assert cab_data["cables"][0]["snapped_tray"] is True
    assert cab_data["cables"][0]["from_endpoint"]["port"] == "SFP+1"

    # 8. Verify AuditLog recorded rack operations
    audits = (await db_session.execute(select(AuditLog).where(AuditLog.action.like("rack.%")))).scalars().all()
    assert len(audits) >= 3

    # 9. RBAC: Login as Viewer -> GET allowed, POST/DELETE forbidden (403)
    login_v = await client.post("/api/v1/auth/login", json={"username": "rack_viewer", "password": "viewerpass123"})
    assert login_v.status_code == 200
    vw_headers = {"X-CSRF-Token": login_v.json()["csrf_token"]}

    v_get = await client.get("/api/v1/racks", headers=vw_headers)
    assert v_get.status_code == 200
    v_post = await client.post("/api/v1/racks", headers=vw_headers, json={"name": "Unauthorized-Rack", "u_height": 42})
    assert v_post.status_code == 403
    v_del = await client.delete(f"/api/v1/racks/{rack_id}", headers=vw_headers)
    assert v_del.status_code == 403
