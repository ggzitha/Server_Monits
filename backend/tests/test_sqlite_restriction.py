import pytest
from backend.app.core.config import settings


@pytest.mark.asyncio
async def test_sqlite_restricted_in_production(client, monkeypatch):
    # Set APP_ENV to production and DEBUG to False
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "DEBUG", False)

    # 1. SQLite connection test in production must be rejected with 400
    test_res = await client.post("/api/v1/setup/test-db", json={
        "db_type": "sqlite",
        "db_name": "prod_sqlite",
    })
    assert test_res.status_code == 400
    assert "restricted" in test_res.json()["detail"].lower()

    # 2. SQLite initialize in production must be rejected with 400
    init_res = await client.post("/api/v1/setup/initialize", json={
        "db_type": "sqlite",
        "db_name": "prod_sqlite",
        "admin_username": "admin",
        "admin_password": "securepassword123",
        "admin_email": "admin@datacenter.internal",
    })
    assert init_res.status_code == 400
    assert "restricted" in init_res.json()["detail"].lower()

