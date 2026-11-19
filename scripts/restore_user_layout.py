#!/usr/bin/env python3
"""
Seed/restore the user's exact 2-room Data Center layout into server_monits_dev.db:
- Server Room (5m x 3m) with 2 Server Racks, 2 Rack Thermohygrometers, and 3 Front Thermohygrometers (5 total)
- Hardening / Staging Room (3m x 3m) right next to Server Room with Table, PC, and Wall-Mounted TV
- Connecting Door between Hardening/Staging Room and Server Room
- AC Outdoor Units outside behind the back wall of Server Room
"""
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

DB_PATH = "server_monits_dev.db"

SENSORS = [
    {
        "identifier": "rack_01_env",
        "name": "Rack 01 Thermohygrometer",
        "area_id": "server_room",
        "x": 1.5,
        "z": 0.85,
        "y": 1.85,
        "temp": 22.4,
        "hum": 44.0,
        "power_kw": 8.2,
    },
    {
        "identifier": "rack_02_env",
        "name": "Rack 02 Thermohygrometer",
        "area_id": "server_room",
        "x": 2.8,
        "z": 0.85,
        "y": 1.85,
        "temp": 23.1,
        "hum": 43.2,
        "power_kw": 9.1,
    },
    {
        "identifier": "front_rack_left_env",
        "name": "Front Rack Left Thermohygrometer",
        "area_id": "server_room",
        "x": 1.1,
        "z": 2.0,
        "y": 1.5,
        "temp": 20.8,
        "hum": 46.5,
        "power_kw": None,
    },
    {
        "identifier": "front_rack_center_env",
        "name": "Front Rack Center Thermohygrometer",
        "area_id": "server_room",
        "x": 2.15,
        "z": 2.0,
        "y": 1.5,
        "temp": 21.2,
        "hum": 45.8,
        "power_kw": None,
    },
    {
        "identifier": "front_rack_right_env",
        "name": "Front Rack Right Thermohygrometer",
        "area_id": "server_room",
        "x": 3.2,
        "z": 2.0,
        "y": 1.5,
        "temp": 21.0,
        "hum": 46.0,
        "power_kw": None,
    },
]

BUILDING = {
    "version": 1,
    "settings": {
        "wall_exterior": 0.25,
        "wall_interior": 0.15,
        "grid": 0.1,
        "roof": {"type": "none"},
    },
    "floors": [
        {
            "id": "ground",
            "name": "Ground Floor",
            "elevation": 0,
            "height": 3.2,
            "cut_height": 1.4,
            "ha_floor": "ground",
            "background": None,
            "outdoor": [],
            "rooms": [
                {
                    "id": "room_server",
                    "name": "Server Room (5x3m)",
                    "ha_area": "server_room",
                    "area_id": "server_room",
                    "points": [[0, 0], [5, 0], [5, 3], [0, 3]],
                    "floor_material": "tiles",
                    "climate": {
                        "temperature": "sensor.front_rack_center_env_temp",
                        "humidity": "sensor.front_rack_center_env_humidity",
                    },
                },
                {
                    "id": "room_hardening",
                    "name": "Hardening / Staging Room (3x3m)",
                    "ha_area": "hardening_staging",
                    "area_id": "hardening_staging",
                    "points": [[5, 0], [8, 0], [8, 3], [5, 3]],
                    "floor_material": "oak",
                },
            ],
            "openings": [
                {
                    "id": "door_staging_to_server",
                    "room_id": "room_server",
                    "edge": 1,
                    "offset": 1.5,
                    "width": 0.9,
                    "height": 2.1,
                    "sill": 0,
                    "type": "door",
                    "hinge": "left",
                    "leaves": 1,
                    "swing": "in",
                    "lock": None,
                    "contact": None,
                    "contact2": None,
                    "cover": None,
                    "tilt": None,
                },
                {
                    "id": "door_staging_entry",
                    "room_id": "room_hardening",
                    "edge": 2,
                    "offset": 1.5,
                    "width": 0.9,
                    "height": 2.1,
                    "sill": 0,
                    "type": "door",
                    "hinge": "right",
                    "leaves": 1,
                    "swing": "in",
                    "lock": None,
                    "contact": None,
                    "contact2": None,
                    "cover": None,
                    "tilt": None,
                },
            ],
            "walls": [],
            "furniture": [
                # 2 Server Racks inside Server Room
                {
                    "id": "srv_rack_01",
                    "type": "pack:dcim.facility:rack_42u",
                    "name": "Server Rack 01",
                    "show_name": True,
                    "x": 1.5,
                    "z": 0.75,
                    "w": 0.6,
                    "d": 1.0,
                    "h": 2.0,
                    "rotation": 0,
                    "variant": "obsidian",
                },
                {
                    "id": "srv_rack_02",
                    "type": "pack:dcim.facility:rack_42u",
                    "name": "Server Rack 02",
                    "show_name": True,
                    "x": 2.8,
                    "z": 0.75,
                    "w": 0.6,
                    "d": 1.0,
                    "h": 2.0,
                    "rotation": 0,
                    "variant": "obsidian",
                },
                # 5 Thermohygrometer Units inside Server Room (2 on racks + 3 in front of racks)
                *[
                    {
                        "id": f"sensor_unit_{s['identifier']}",
                        "type": "pack:dcim.facility:thermohygro_sensor",
                        "name": s["name"],
                        "show_name": True,
                        "x": s["x"],
                        "z": s["z"],
                        "w": 0.20,
                        "d": 0.08,
                        "h": 0.24,
                        "mount_y": s["y"],
                        "rotation": 0,
                    }
                    for s in SENSORS
                ],
                # Hardening / Staging Room: Table, PC, Chair, and Wall-Mounted TV
                {
                    "id": "staging_table",
                    "type": "desk",
                    "name": "Hardening Table",
                    "show_name": True,
                    "x": 6.5,
                    "z": 0.85,
                    "w": 1.4,
                    "d": 0.7,
                    "h": 0.75,
                    "rotation": 0,
                },
                {
                    "id": "staging_pc",
                    "type": "pack:dcim.facility:pc_workstation",
                    "name": "Hardening PC",
                    "show_name": True,
                    "x": 6.5,
                    "z": 0.80,
                    "w": 0.65,
                    "d": 0.45,
                    "h": 0.45,
                    "mount_y": 0.75,
                    "rotation": 0,
                },
                {
                    "id": "staging_chair",
                    "type": "office_chair",
                    "name": "Chair",
                    "x": 6.5,
                    "z": 1.55,
                    "w": 0.65,
                    "d": 0.65,
                    "h": 1.1,
                    "rotation": 180,
                },
                {
                    "id": "staging_tv_wall",
                    "type": "tv_wall",
                    "name": "Wall-Mounted TV",
                    "show_name": True,
                    "x": 7.86,
                    "z": 1.5,
                    "w": 1.3,
                    "d": 0.08,
                    "h": 0.75,
                    "mount_y": 1.45,
                    "rotation": 270,
                },
                # Outside in back of Server Room: 2 AC Outdoor Units
                {
                    "id": "ac_outdoor_1",
                    "type": "pack:dcim.facility:ac_outdoor_unit",
                    "name": "AC Outdoor Unit 1",
                    "show_name": True,
                    "x": 1.5,
                    "z": -0.55,
                    "w": 0.9,
                    "d": 0.36,
                    "h": 0.75,
                    "mount_y": 0.15,
                    "rotation": 180,
                },
                {
                    "id": "ac_outdoor_2",
                    "type": "pack:dcim.facility:ac_outdoor_unit",
                    "name": "AC Outdoor Unit 2",
                    "show_name": True,
                    "x": 2.8,
                    "z": -0.55,
                    "w": 0.9,
                    "d": 0.36,
                    "h": 0.75,
                    "mount_y": 0.15,
                    "rotation": 180,
                },
            ],
            "placements": [
                {"entity_id": "light.server_alpha_light", "x": 2.5, "z": 1.5, "y": 3.0, "mount": "ceiling", "name": "Server Room Light", "show_name": True, "marker": "always"},
                {"entity_id": "light.noc_light", "x": 6.5, "z": 1.5, "y": 3.0, "mount": "ceiling", "name": "Hardening Room Light", "show_name": True, "marker": "always"},
                *[
                    {"entity_id": f"sensor.{s['identifier']}_temp", "x": s["x"], "z": s["z"], "y": s["y"], "name": f"{s['name']} Temp", "show_name": True, "marker": "always"}
                    for s in SENSORS
                ],
                *[
                    {"entity_id": f"sensor.{s['identifier']}_humidity", "x": round(s["x"] + 0.32, 2), "z": s["z"], "y": s["y"], "name": f"{s['name']} Humidity", "show_name": True, "marker": "always"}
                    for s in SENSORS
                ],
            ],
        }
    ],
}


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    areas = {
        "server_room": {"area_id": "server_room", "name": "Server Room (5x3m)", "floor_id": "ground"},
        "hardening_staging": {"area_id": "hardening_staging", "name": "Hardening / Staging Room (3x3m)", "floor_id": "ground"},
    }

    record = {
        "building": BUILDING,
        "name": "Server Room & Hardening Facility",
        "site": "Main Data Center",
        "areas": areas,
        "snapshots": [],
        "revision": 1,
        "updated_at": now_iso,
    }

    cur.execute(
        "INSERT OR REPLACE INTO system_config (key, value, updated_at) VALUES (?, ?, ?)",
        ("active_3d_building", json.dumps(record), now_iso),
    )

    cur.execute("DELETE FROM floor_plans")
    cur.execute(
        """
        INSERT INTO floor_plans (id, name, site_name, level_index, grid_size_meters, scale_ratio, metadata_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            "Server Room & Hardening Facility",
            "Main Data Center",
            0,
            0.5,
            1.0,
            json.dumps(BUILDING),
            now_iso,
            now_iso,
        ),
    )

    # Replace sensors with the 5 exact Server Room thermohygrometers + 24h telemetry history
    cur.execute("DELETE FROM telemetry_readings")
    cur.execute("DELETE FROM sensors")

    for s in SENSORS:
        sid = str(uuid.uuid4())
        meta = {
            "area_id": s["area_id"],
            "floor_id": "ground",
            "placement_x": s["x"],
            "placement_z": s["z"],
            "placement_y": s["y"],
            "power_kw": s["power_kw"],
        }
        cur.execute(
            """
            INSERT INTO sensors (
                id, identifier, name, sensor_type, current_temperature, current_humidity,
                battery_level, status, last_seen_at, is_discovered,
                temp_max_warning, temp_max_critical, humidity_max_warning, humidity_max_critical,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                s["identifier"],
                s["name"],
                "thermohygrometer",
                s["temp"],
                s["hum"],
                98.0,
                "online",
                now_iso,
                0,
                27.0,
                32.0,
                60.0,
                75.0,
                json.dumps(meta),
                now_iso,
                now_iso,
            ),
        )

        for step in range(24):
            ts = (now - timedelta(hours=23 - step)).isoformat()
            wave = ((step % 5) - 2) * 0.35
            cur.execute(
                """
                INSERT INTO telemetry_readings (sensor_id, timestamp, temperature, humidity, raw_data)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    ts,
                    round(s["temp"] + wave, 2),
                    round(s["hum"] - wave * 1.4, 2),
                    json.dumps(meta),
                ),
            )

    conn.commit()
    conn.close()
    print("Saved user's 2-room facility layout & 5 thermohygrometers to server_monits_dev.db!")


if __name__ == "__main__":
    main()
