import secrets
import pytest
from sqlalchemy import select, func
from backend.app.core.security import hash_password, verify_password, get_totp_code
from backend.app.db.models.user import User, Role
from backend.app.db.models.auth_tokens import LoginAttempt, TwoFactorSecret
from backend.app.db.models.system_config import SystemConfig


@pytest.mark.asyncio
async def test_argon2_password_hashing():
    pwd = secrets.token_urlsafe(16)
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrong_password", hashed) is False


@pytest.mark.asyncio
async def test_login_and_session_cookie(client, db_session):
    admin_password = "P@" + secrets.token_urlsafe(14)
    role_res = await db_session.execute(select(Role).where(Role.name == "Admin"))
    admin_role = role_res.scalar_one()

    admin = User(
        username="admin",
        email="admin@test.com",
        password_hash=hash_password(admin_password),
        is_active=True,
    )
    admin.roles.append(admin_role)
    db_session.add(admin)
    db_session.add(SystemConfig(key="is_initialized", value="true"))
    await db_session.commit()

    # Attempt login with wrong password
    bad_res = await client.post("/api/v1/auth/login", json={
        "username": "admin",
        "password": "wrongpassword123",
    })
    assert bad_res.status_code == 401

    # Verify attempt logged in DB
    att_res = await db_session.execute(select(func.count(LoginAttempt.id)).where(LoginAttempt.username == "admin"))
    assert att_res.scalar_one() >= 1

    # Attempt login with correct password
    login_res = await client.post("/api/v1/auth/login", json={
        "username": "admin",
        "password": admin_password,
    })
    assert login_res.status_code == 200
    data = login_res.json()
    assert data["requires_2fa"] is False
    assert "access_token" in data
    assert "csrf_token" in data
    assert data["user"]["username"] == "admin"
    assert "Admin" in data["user"]["roles"]

    # Verify session cookie was set
    assert "monit_session" in client.cookies

    # Test /api/v1/auth/me
    me_res = await client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["username"] == "admin"


@pytest.mark.asyncio
async def test_database_backed_rate_limiting_lockout(client, db_session):
    test_user_pass = "P@" + secrets.token_urlsafe(14)
    viewer_role = (await db_session.execute(select(Role).where(Role.name == "Viewer"))).scalar_one()

    user = User(
        username="lockout_user",
        email="lockout@test.com",
        password_hash=hash_password(test_user_pass),
        is_active=True,
    )
    user.roles.append(viewer_role)
    db_session.add(user)
    db_session.add(SystemConfig(key="is_initialized", value="true"))
    await db_session.commit()

    # Trigger 5 failed attempts
    for _ in range(5):
        res = await client.post("/api/v1/auth/login", json={
            "username": "lockout_user",
            "password": "invalid_password",
        })
        assert res.status_code in (401, 403)

    # 6th attempt should be blocked with 403 by DB-backed lockout state
    locked_res = await client.post("/api/v1/auth/login", json={
        "username": "lockout_user",
        "password": test_user_pass,  # Even with correct password, blocked by lockout!
    })
    assert locked_res.status_code == 403
    assert "locked" in locked_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_two_factor_auth_totp_and_single_use_backup_codes(client, db_session):
    viewer_role = (await db_session.execute(select(Role).where(Role.name == "Viewer"))).scalar_one()
    user_pass = "P@" + secrets.token_urlsafe(14)

    user = User(
        username="test2fa_backup",
        email="2fa_backup@test.com",
        password_hash=hash_password(user_pass),
        is_active=True,
    )
    user.roles.append(viewer_role)
    db_session.add(user)
    db_session.add(SystemConfig(key="is_initialized", value="true"))
    await db_session.commit()

    # 1. Login first to configure 2FA
    login_res = await client.post("/api/v1/auth/login", json={
        "username": "test2fa_backup",
        "password": user_pass,
    })
    assert login_res.status_code == 200
    csrf_token = login_res.json()["csrf_token"]

    # 2. Setup 2FA -> receive secret AND recovery backup codes
    setup_res = await client.post("/api/v1/auth/2fa/setup", headers={"X-CSRF-Token": csrf_token})
    assert setup_res.status_code == 200
    data = setup_res.json()
    secret = data["secret"]
    backup_codes = data["backup_codes"]
    assert len(backup_codes) == 8

    # Confirm 2FA with valid TOTP code
    confirm_code = get_totp_code(secret)
    confirm_res = await client.post(
        "/api/v1/auth/2fa/confirm",
        json={"totp_code": confirm_code},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert confirm_res.status_code == 200

    # Logout
    await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})

    # 3. Login step 1: requires 2FA
    l_res = await client.post("/api/v1/auth/login", json={
        "username": "test2fa_backup",
        "password": user_pass,
    })
    assert l_res.status_code == 200
    temp_token = l_res.json()["temp_token"]

    # 4. Login step 2 using FIRST backup code
    chosen_backup = backup_codes[0]
    verify_backup_res = await client.post("/api/v1/auth/2fa/verify", json={
        "temp_token": temp_token,
        "code": chosen_backup,
    })
    assert verify_backup_res.status_code == 200
    assert verify_backup_res.json()["used_backup_code"] is True
    assert verify_backup_res.json()["remaining_backup_codes"] == 7

    # Logout again
    await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": verify_backup_res.json()["csrf_token"]})

    # 5. Login step 1 again
    l_res2 = await client.post("/api/v1/auth/login", json={
        "username": "test2fa_backup",
        "password": user_pass,
    })
    temp_token2 = l_res2.json()["temp_token"]

    # 6. Attempt to RE-USE the same backup code -> MUST FAIL (single-use!)
    reuse_res = await client.post("/api/v1/auth/2fa/verify", json={
        "temp_token": temp_token2,
        "code": chosen_backup,
    })
    assert reuse_res.status_code == 400
    assert "invalid" in reuse_res.json()["detail"].lower()

    # 7. Use second backup code -> MUST SUCCEED
    chosen_backup_2 = backup_codes[1]
    verify_backup_res2 = await client.post("/api/v1/auth/2fa/verify", json={
        "temp_token": temp_token2,
        "code": chosen_backup_2,
    })
    assert verify_backup_res2.status_code == 200
    assert verify_backup_res2.json()["used_backup_code"] is True
    assert verify_backup_res2.json()["remaining_backup_codes"] == 6
