"""
test_sensors_and_virtual.py - Backend tests for DB-backed sensors, time-series telemetry, and virtual lights/layers.
"""
import pytest
from sqlalchemy import select
from backend.app.core.security import hash_password
from backend.app.db.models.user import User, Role
from backend.app.db.models.system_config import SystemConfig


@pytest.mark.asyncio
async def test_db_sensors_and_virtual_states(client, db_session):
    admin_role = (await db_session.execute(select(Role).where(Role.name == "Admin"))).scalar_one()
    admin = User(
        username="admin_sensor_tester",
        email="adm_sensor@test.com",
        password_hash=hash_password("adminpass123"),
        is_active=True,
    )
    admin.roles.append(admin_role)
    db_session.add(admin)
    db_session.add(SystemConfig(key="is_initialized", value="true"))
    await db_session.commit()

    login_res = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin_sensor_tester", "password": "adminpass123"},
    )
    assert login_res.status_code == 200
    csrf_token = login_res.json()["csrf_token"]
    admin_headers = {"X-CSRF-Token": csrf_token}

    # 1. List sensors (auto-seeds 8 default Data Center sensors)
    res = await client.get("/api/v1/sensors", headers=admin_headers)
    assert res.status_code == 200
    sensors = res.json()
    assert len(sensors) >= 8
    alpha = next(s for s in sensors if s["identifier"] == "server_alpha_env")
    assert alpha["area_id"] == "server_alpha"

    # 2. Push direct sensor reading into DB
    push_res = await client.post(
        "/api/v1/sensors/readings",
        headers=admin_headers,
        json={
            "identifier": "server_alpha_env",
            "area_id": "server_alpha",
            "temperature": 25.4,
            "humidity": 48.2,
            "power_kw": 51.0,
        },
    )
    assert push_res.status_code == 200
    pushed = push_res.json()
    assert pushed["temperature"] == 25.4
    assert pushed["humidity"] == 48.2

    # 3. Verify history sparkline endpoint
    hist_res = await client.get("/api/v1/sensors/server_alpha_env/history", headers=admin_headers)
    assert hist_res.status_code == 200
    hist = hist_res.json()
    assert len(hist["readings"]) >= 1
    assert hist["readings"][-1]["temperature"] == 25.4

    # 4. Persist virtual light & cable layer state
    v_post = await client.post(
        "/api/v1/sensors/virtual/states",
        headers=admin_headers,
        json={
            "entity_id": "light.server_alpha_light",
            "state": "off",
            "attributes": {"brightness": 180, "rgb_color": [0, 240, 255]},
        },
    )
    assert v_post.status_code == 200

    v_get = await client.get("/api/v1/sensors/virtual/states", headers=admin_headers)
    assert v_get.status_code == 200
    states = v_get.json()["states"]
    assert states["light.server_alpha_light"]["state"] == "off"

    # 5. Place new sensor at specific 3D coordinates (x, z, y) and verify persistence
    place_res = await client.post(
        "/api/v1/sensors/readings",
        headers=admin_headers,
        json={
            "identifier": "cold_aisle_b09",
            "name": "Cold Aisle Rack B09",
            "area_id": "server_alpha",
            "floor_id": "ground",
            "placement_x": 4.2,
            "placement_z": 3.1,
            "placement_y": 1.6,
            "temperature": 19.8,
            "humidity": 42.5,
        },
    )
    assert place_res.status_code == 200
    list_res2 = await client.get("/api/v1/sensors", headers=admin_headers)
    placed_sensor = next(s for s in list_res2.json() if s["identifier"] == "cold_aisle_b09")
    assert placed_sensor["placement_x"] == 4.2
    assert placed_sensor["placement_z"] == 3.1
    assert placed_sensor["placement_y"] == 1.6
    assert placed_sensor["current_temperature"] == 19.8
    assert placed_sensor["current_humidity"] == 42.5

    # 6. Save and load active 3D building state (/api/v1/sensors/building)
    sample_building = {
        "version": 1,
        "settings": {"grid": 0.1},
        "floors": [
            {
                "id": "ground",
                "name": "Ground Floor",
                "rooms": [{"id": "r1", "name": "Server Room Alpha", "points": [[0, 0], [8, 0], [8, 6], [0, 6]]}],
                "walls": [],
                "furniture": [],
                "placements": [{"entity_id": "sensor.cold_aisle_b09_temp", "x": 4.2, "z": 3.1}],
            }
        ],
    }
    b_post = await client.post(
        "/api/v1/sensors/building",
        headers=admin_headers,
        json={"building": sample_building, "name": "Test Datacenter", "revision": 5},
    )
    assert b_post.status_code == 200
    assert b_post.json()["status"] == "saved"

    b_get = await client.get("/api/v1/sensors/building", headers=admin_headers)
    assert b_get.status_code == 200
    b_data = b_get.json()
    assert b_data["saved"] is True
    assert b_data["name"] == "Test Datacenter"
    assert b_data["building"]["floors"][0]["rooms"][0]["name"] == "Server Room Alpha"

    # 7. Separated sensor types (ammeter, voltmeter, power_meter)
    amp_res = await client.post(
        "/api/v1/sensors/readings",
        headers=admin_headers,
        json={
            "identifier": "pdu_a_ammeter",
            "name": "PDU A Ammeter",
            "sensor_type": "ammeter",
            "area_id": "server_alpha",
            "amperes": 14.5,
        },
    )
    assert amp_res.status_code == 200

    volt_res = await client.post(
        "/api/v1/sensors/readings",
        headers=admin_headers,
        json={
            "identifier": "pdu_a_voltmeter",
            "name": "PDU A Voltmeter",
            "sensor_type": "voltmeter",
            "area_id": "server_alpha",
            "volts": 229.4,
        },
    )
    assert volt_res.status_code == 200

    list_res3 = await client.get("/api/v1/sensors", headers=admin_headers)
    by_id = {s["identifier"]: s for s in list_res3.json()}
    assert by_id["pdu_a_ammeter"]["sensor_type"] == "ammeter"
    assert by_id["pdu_a_ammeter"]["amperes"] == 14.5
    assert by_id["pdu_a_ammeter"]["power_kw"] is None
    assert by_id["pdu_a_voltmeter"]["sensor_type"] == "voltmeter"
    assert by_id["pdu_a_voltmeter"]["volts"] == 229.4

    # 8. Grafana-style read-only SQLite query-draft endpoint
    import sqlite3, tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE rtime_suhu (Date_Time TEXT, Temperature REAL)")
    conn.execute("INSERT INTO rtime_suhu VALUES ('2026-11-19 10:00:00', 22.4)")
    conn.commit()
    conn.close()

    q_ok = await client.post(
        "/api/v1/data-sources/query-draft",
        headers=admin_headers,
        params={"source_type": "sqlite", "database": db_path},
        json={
            "query": 'SELECT Date_Time AS "time", Temperature FROM rtime_suhu',
            "format": "time_series",
        },
    )
    assert q_ok.status_code == 200
    q_data = q_ok.json()
    assert q_data["row_count"] == 1
    assert q_data["rows"][0]["Temperature"] == 22.4

    q_bad = await client.post(
        "/api/v1/data-sources/query-draft",
        headers=admin_headers,
        params={"source_type": "sqlite", "database": db_path},
        json={
            "query": "DELETE FROM rtime_suhu",
            "format": "table",
        },
    )
    assert q_bad.status_code == 400


