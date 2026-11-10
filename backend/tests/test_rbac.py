import pytest
from sqlalchemy import select
from backend.app.core.security import hash_password
from backend.app.db.models.user import User, Role
from backend.app.db.models.system_config import SystemConfig


@pytest.mark.asyncio
async def test_rbac_admin_vs_viewer_permissions(client, db_session):
    # Fetch roles
    roles = (await db_session.execute(select(Role))).scalars().all()
    role_map = {r.name: r for r in roles}

    # Create Admin
    admin = User(
        username="admin_user",
        email="admin@corp.com",
        password_hash=hash_password("adminpass123"),
        is_active=True,
    )
    admin.roles.append(role_map["Admin"])
    db_session.add(admin)

    # Create Viewer
    viewer = User(
        username="viewer_user",
        email="viewer@corp.com",
        password_hash=hash_password("viewerpass123"),
        is_active=True,
    )
    viewer.roles.append(role_map["Viewer"])
    db_session.add(viewer)
    db_session.add(SystemConfig(key="is_initialized", value="true"))
    await db_session.commit()

    # 1. Login as Viewer
    view_login = await client.post("/api/v1/auth/login", json={
        "username": "viewer_user",
        "password": "viewerpass123",
    })
    viewer_csrf = view_login.json()["csrf_token"]

    # Viewer attempts to list users -> 403 Forbidden
    view_users_res = await client.get("/api/v1/users")
    assert view_users_res.status_code == 403

    # Viewer attempts to create user -> 403 Forbidden
    create_res = await client.post("/api/v1/users", json={
        "username": "hack_user",
        "email": "hack@corp.com",
        "password": "password123",
    }, headers={"X-CSRF-Token": viewer_csrf})
    assert create_res.status_code == 403

    # 2. Login as Admin
    admin_login = await client.post("/api/v1/auth/login", json={
        "username": "admin_user",
        "password": "adminpass123",
    })
    admin_csrf = admin_login.json()["csrf_token"]

    # Admin lists users -> 200 OK
    admin_users_res = await client.get("/api/v1/users")
    assert admin_users_res.status_code == 200
    assert admin_users_res.json()["total"] >= 2

    # Admin creates new user -> 200 OK
    new_user_res = await client.post("/api/v1/users", json={
        "username": "operator1",
        "email": "op1@corp.com",
        "password": "password123",
        "role_names": ["Operator"],
    }, headers={"X-CSRF-Token": admin_csrf})
    assert new_user_res.status_code == 200
    assert new_user_res.json()["username"] == "operator1"

