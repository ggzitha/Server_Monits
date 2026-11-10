import secrets
import pytest
from sqlalchemy import select
from backend.app.db.models.system_config import SystemConfig
from backend.app.db.models.user import User


@pytest.mark.asyncio
async def test_setup_flow_and_post_init_lockdown(client, db_session):
    # Dynamically generated password for test
    dynamic_admin_pass = "P@" + secrets.token_urlsafe(16)

    # 1. Test connection to SQLite
    test_res = await client.post("/api/v1/setup/test-db", json={
        "db_type": "sqlite",
        "db_name": "test_setup_temp",
    })
    assert test_res.status_code == 200
    assert test_res.json()["success"] is True

    # 2. Initialize system (providing in-memory custom URL for isolated test execution)
    init_res = await client.post("/api/v1/setup/initialize", json={
        "db_type": "sqlite",
        "custom_url": "sqlite+aiosqlite:///:memory:",
        "admin_username": "admin",
        "admin_password": dynamic_admin_pass,
        "admin_email": "admin@datacenter.internal",
        "default_language": "id",
        "default_theme": "neon",
    })
    assert init_res.status_code == 200
    assert init_res.json()["success"] is True

    # 3. Post-initialization lockdown test (Requirement 3: Setup endpoints return 403)
    locked_test = await client.post("/api/v1/setup/test-db", json={
        "db_type": "sqlite",
        "db_name": "temp",
    })
    assert locked_test.status_code == 403

    locked_init = await client.post("/api/v1/setup/initialize", json={
        "db_type": "sqlite",
        "db_name": "temp",
    })
    assert locked_init.status_code == 403
