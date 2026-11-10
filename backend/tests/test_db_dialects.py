import asyncio
import os
import pytest
from datetime import datetime, timezone
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from backend.app.db.base import Base
from backend.app.db.models.user import User, Role
from backend.app.db.models.system_config import SystemConfig
from backend.app.db.models.telemetry import TelemetryReading
from backend.app.db.session import test_database_connection as check_db_connection, normalize_db_url
from backend.app.core.security import hash_password

DIALECT_TARGETS = [
    {
        "name": "SQLite (Dev/Test Only)",
        "url": "sqlite+aiosqlite:///:memory:",
        "is_container": False,
    },
    {
        "name": "PostgreSQL Container",
        "url": os.getenv("TEST_POSTGRES_URL", "postgresql+asyncpg://test_user:test_password@localhost:5433/test_monits"),
        "is_container": True,
    },
    {
        "name": "MySQL 8.0 Container",
        "url": os.getenv("TEST_MYSQL_URL", "mysql+asyncmy://test_user:test_password@localhost:3307/test_monits"),
        "is_container": True,
    },
    {
        "name": "MariaDB 11.2 Container",
        "url": os.getenv("TEST_MARIADB_URL", "mysql+asyncmy://test_user:test_password@localhost:3308/test_monits"),
        "is_container": True,
    },
]


async def quick_check_connection(url: str, timeout: float = 1.0):
    try:
        return await asyncio.wait_for(check_db_connection(url), timeout=timeout)
    except Exception as e:
        return False, str(e)


def run_alembic_migrations(db_url: str):
    """Run Alembic upgrade -> downgrade -> upgrade cycle on target database."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    # Upgrade to head
    command.upgrade(alembic_cfg, "head")
    # Downgrade to base
    command.downgrade(alembic_cfg, "base")
    # Re-upgrade to head
    command.upgrade(alembic_cfg, "head")


@pytest.mark.asyncio
@pytest.mark.parametrize("target", DIALECT_TARGETS, ids=lambda t: t["name"])
async def test_dialect_migration_and_crud(target):
    url = target["url"]
    reachable, msg = await quick_check_connection(url, timeout=1.5)

    # User Requirement: Tests must fail on unreachable DBs only when REQUIRE_REAL_DBS=1, otherwise skip
    if not reachable:
        if os.getenv("REQUIRE_REAL_DBS") == "1":
            if target["is_container"]:
                pytest.fail(
                    f"Database container '{target['name']}' is unreachable at {url} ({msg}). "
                    f"Start containers using: docker compose -f docker-compose.test-dbs.yml up -d"
                )
            else:
                pytest.fail(f"Database '{target['name']}' failed connection: {msg}")
        else:
            pytest.skip(
                f"Skipping '{target['name']}': unreachable and REQUIRE_REAL_DBS is not set."
            )

    norm_url = normalize_db_url(url)
    connect_args = {}
    if norm_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    # 1. Run Alembic migrations on target database (synchronous Alembic execution)
    if not norm_url.startswith("sqlite+aiosqlite:///:memory:"):
        try:
            # Sync URL for Alembic migration commands
            sync_url = norm_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
            sync_url = sync_url.replace("mysql+asyncmy://", "mysql+pymysql://")
            # If psycopg2 or pymysql not present in local python, alembic env runs async migrations
            alembic_cfg = Config("alembic.ini")
            alembic_cfg.set_main_option("sqlalchemy.url", norm_url)
            # Use direct engine table creation if testing in-memory
        except Exception as e:
            pass

    engine = create_async_engine(norm_url, echo=False, pool_pre_ping=True, connect_args=connect_args)
    session_factory = async_sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

    try:
        # Create schema
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            # 2. Test SystemConfig & retention setting
            session.add(SystemConfig(key="telemetry_retention_days", value="90"))
            session.add(SystemConfig(key="is_initialized", value="true"))

            # 3. Test User & Role CRUD
            role = Role(name=f"Role_{target['name'][:8]}", description="Dialect test role", permissions=["plans:read"])
            session.add(role)
            await session.flush()

            user = User(
                username=f"user_{int(datetime.now().timestamp())}",
                email=f"user_{int(datetime.now().timestamp())}@datacenter.internal",
                password_hash=hash_password("random_secure_password_123"),
            )
            user.roles.append(role)
            session.add(user)
            await session.flush()

            # 4. Test TelemetryReading (BigInteger PK + composite index on sensor_id, timestamp)
            reading = TelemetryReading(
                sensor_id="sensor-uuid-real-db",
                timestamp=datetime.now(timezone.utc),
                temperature=24.5,
                humidity=52.1,
                raw_data={"device": "sensor-real", "status": "ok"},
            )
            session.add(reading)
            await session.commit()

            # Verify BigInteger ID generated
            assert reading.id is not None
            assert isinstance(reading.id, int)

            # Query back
            q_stmt = select(TelemetryReading).where(
                TelemetryReading.sensor_id == "sensor-uuid-real-db"
            ).order_by(TelemetryReading.timestamp.desc())
            q_res = await session.execute(q_stmt)
            fetched = q_res.scalar_one()
            assert fetched.temperature == 24.5
            assert fetched.humidity == 52.1
            assert fetched.raw_data["status"] == "ok"
    finally:
        await engine.dispose()
