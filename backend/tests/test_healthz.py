import pytest


@pytest.mark.asyncio
async def test_healthz_endpoint(client):
    res = await client.get("/healthz")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "database" in data
    assert "timestamp" in data

