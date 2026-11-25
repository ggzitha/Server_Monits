"""
test_alerts_reports.py - Phase 7 unit & integration tests:
- Pure threshold rule evaluator (`evaluate_rule_value`)
- Threshold Alert Rules full CRUD (`/api/v1/alerts/rules`)
- Live Threshold Evaluator (`POST /api/v1/alerts/evaluate`) with deduplication
- Incident Timeline full CRUD (`/api/v1/alerts/incidents`)
- Executive & SLA Reports (`/api/v1/alerts/reports/summary` & `/export?format=csv|json|html`)
- RBAC enforcement (Viewer read-only vs Admin write), AuditLog recording, /ready probe & security headers.
"""
import pytest
from sqlalchemy import select

from backend.app.api.v1.alerts import evaluate_rule_value
from backend.app.core.security import hash_password
from backend.app.db.models.audit import AuditLog
from backend.app.db.models.sensor import Sensor
from backend.app.db.models.system_config import SystemConfig
from backend.app.db.models.user import Role, User


def test_evaluate_rule_value_operators():
    # gt
    assert evaluate_rule_value(31.0, "gt", 27.0, 30.0) == ("critical", 30.0)
    assert evaluate_rule_value(28.5, "gt", 27.0, 30.0) == ("warning", 27.0)
    assert evaluate_rule_value(24.0, "gt", 27.0, 30.0) == (None, None)
    # gte
    assert evaluate_rule_value(30.0, "gte", 27.0, 30.0) == ("critical", 30.0)
    assert evaluate_rule_value(27.0, "gte", 27.0, 30.0) == ("warning", 27.0)
    # lt (ESD low humidity)
    assert evaluate_rule_value(18.0, "lt", 30.0, 20.0) == ("critical", 20.0)
    assert evaluate_rule_value(25.0, "lt", 30.0, 20.0) == ("warning", 30.0)
    assert evaluate_rule_value(45.0, "lt", 30.0, 20.0) == (None, None)
    # lte & None
    assert evaluate_rule_value(20.0, "lte", 30.0, 20.0) == ("critical", 20.0)
    assert evaluate_rule_value(None, "gt", 27.0, 30.0) == (None, None)


@pytest.mark.asyncio
async def test_alerts_rules_incidents_reports_rbac_and_hardening(client, db_session):
    admin_role = (await db_session.execute(select(Role).where(Role.name == "Admin"))).scalar_one()
    viewer_role = (await db_session.execute(select(Role).where(Role.name == "Viewer"))).scalar_one()

    admin = User(username="al_admin", email="al_admin@test.com", password_hash=hash_password("adminpass123"), is_active=True)
    admin.roles.append(admin_role)
    viewer = User(username="al_viewer", email="al_viewer@test.com", password_hash=hash_password("viewerpass123"), is_active=True)
    viewer.roles.append(viewer_role)
    hot_sensor = Sensor(
        name="Hot Aisle Sensor 01",
        identifier="hot_aisle_01",
        sensor_type="temperature_humidity",
        current_temperature=33.5,
        current_humidity=48.0,
        status="online",
    )
    db_session.add_all([admin, viewer, hot_sensor, SystemConfig(key="is_initialized", value="true")])
    await db_session.commit()

    # 1. Verify /ready probe & production security headers
    ready_res = await client.get("/ready")
    assert ready_res.status_code == 200
    assert ready_res.json()["ready"] is True
    assert ready_res.headers.get("x-content-type-options") == "nosniff"
    assert ready_res.headers.get("x-frame-options") == "SAMEORIGIN"
    assert "strict-origin" in (ready_res.headers.get("referrer-policy") or "")
    assert "camera=()" in (ready_res.headers.get("permissions-policy") or "")

    # Login as Admin
    login_a = await client.post("/api/v1/auth/login", json={"username": "al_admin", "password": "adminpass123"})
    assert login_a.status_code == 200
    adm_headers = {"X-CSRF-Token": login_a.json()["csrf_token"]}

    # 2. List rules (auto-seeds 3 default ASHRAE/ESD rules)
    r_list = await client.get("/api/v1/alerts/rules", headers=adm_headers)
    assert r_list.status_code == 200
    assert r_list.json()["count"] >= 3

    # 3. Create, Update, Delete AlertRule
    r_create = await client.post(
        "/api/v1/alerts/rules",
        headers=adm_headers,
        json={
            "name": "Custom Rack Overheat",
            "target_scope": "all_sensors",
            "metric_type": "temperature",
            "operator": "gt",
            "warning_threshold": 28.0,
            "critical_threshold": 32.0,
            "cooldown_minutes": 10,
            "description": "Custom test rule",
        },
    )
    assert r_create.status_code == 201
    created_rule = r_create.json()
    assert created_rule["name"] == "Custom Rack Overheat"

    r_patch = await client.patch(
        f"/api/v1/alerts/rules/{created_rule['id']}",
        headers=adm_headers,
        json={"critical_threshold": 31.5, "enabled": False},
    )
    assert r_patch.status_code == 200
    assert r_patch.json()["critical_threshold"] == 31.5
    assert r_patch.json()["enabled"] is False

    r_del = await client.delete(f"/api/v1/alerts/rules/{created_rule['id']}", headers=adm_headers)
    assert r_del.status_code == 200
    assert r_del.json()["deleted"] is True

    # 4. Evaluate default rules against hot_sensor (33.5°C > 30°C critical)
    eval1 = await client.post("/api/v1/alerts/evaluate", headers=adm_headers)
    assert eval1.status_code == 200
    assert eval1.json()["triggered"] == 1
    assert eval1.json()["incidents"][0]["severity"] == "critical"

    # Re-evaluating should deduplicate active incident
    eval2 = await client.post("/api/v1/alerts/evaluate", headers=adm_headers)
    assert eval2.status_code == 200
    assert eval2.json()["triggered"] == 0

    # 5. Incident Timeline CRUD (manual create -> patch ack/resolve -> delete)
    inc_create = await client.post(
        "/api/v1/alerts/incidents",
        headers=adm_headers,
        json={
            "sensor_id": hot_sensor.id,
            "metric_type": "humidity",
            "severity": "warning",
            "reading_value": 68.2,
            "threshold_value": 65.0,
            "message": "Manual humidity spike test",
            "comment": "Checking CRAC unit",
        },
    )
    assert inc_create.status_code == 201
    inc_id = inc_create.json()["id"]

    inc_patch = await client.patch(
        f"/api/v1/alerts/incidents/{inc_id}",
        headers=adm_headers,
        json={"status": "resolved", "comment": "CRAC damper adjusted"},
    )
    assert inc_patch.status_code == 200
    assert inc_patch.json()["status"] == "resolved"
    assert inc_patch.json()["resolved_at"] is not None
    assert inc_patch.json()["comment"] == "CRAC damper adjusted"

    inc_list = await client.get("/api/v1/alerts/incidents", headers=adm_headers)
    assert inc_list.status_code == 200
    assert inc_list.json()["count"] >= 2

    inc_del = await client.delete(f"/api/v1/alerts/incidents/{inc_id}", headers=adm_headers)
    assert inc_del.status_code == 200
    assert inc_del.json()["deleted"] is True

    # 6. Reports summary & exports (JSON, CSV, Printable HTML)
    rep_sum = await client.get("/api/v1/alerts/reports/summary", headers=adm_headers)
    assert rep_sum.status_code == 200
    body = rep_sum.json()
    assert body["environment"]["sensor_count"] >= 1
    assert body["incidents"]["active"] >= 1

    rep_csv = await client.get("/api/v1/alerts/reports/export?format=csv", headers=adm_headers)
    assert rep_csv.status_code == 200
    assert "text/csv" in rep_csv.headers["content-type"]
    assert "Hot Aisle Sensor 01" in rep_csv.text

    rep_json = await client.get("/api/v1/alerts/reports/export?format=json", headers=adm_headers)
    assert rep_json.status_code == 200
    assert "application/json" in rep_json.headers["content-type"]

    rep_html = await client.get("/api/v1/alerts/reports/export?format=html", headers=adm_headers)
    assert rep_html.status_code == 200
    assert "text/html" in rep_html.headers["content-type"]
    assert "DCIM Executive" in rep_html.text

    # 7. Verify AuditLog recorded mutations
    audits = (await db_session.execute(select(AuditLog).where(AuditLog.action.like("alert.%")))).scalars().all()
    actions = {a.action for a in audits}
    assert {"alert.rule.create", "alert.rule.update", "alert.rule.delete", "alert.incident.create", "alert.incident.update", "alert.incident.delete"}.issubset(actions)

    # 8. RBAC: Viewer can read & export, cannot mutate
    login_v = await client.post("/api/v1/auth/login", json={"username": "al_viewer", "password": "viewerpass123"})
    assert login_v.status_code == 200
    vw_headers = {"X-CSRF-Token": login_v.json()["csrf_token"]}

    assert (await client.get("/api/v1/alerts/rules", headers=vw_headers)).status_code == 200
    assert (await client.get("/api/v1/alerts/incidents", headers=vw_headers)).status_code == 200
    assert (await client.get("/api/v1/alerts/reports/export?format=csv", headers=vw_headers)).status_code == 200
    assert (await client.post("/api/v1/alerts/evaluate", headers=vw_headers)).status_code == 403
    assert (
        await client.post(
            "/api/v1/alerts/rules",
            headers=vw_headers,
            json={"name": "Nope", "critical_threshold": 40.0},
        )
    ).status_code == 403
