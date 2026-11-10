import asyncio
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Force test configuration
os.environ["APP_ENV"] = "test"
os.environ["DEBUG"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from backend.app.core.config import settings
settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"

from backend.app.db.base import Base
import backend.app.db.models  # ensure models are loaded
from backend.app.db.session import _engine, _session_factory
import backend.app.db.session as session_module
from backend.app.main import app
from backend.app.core.security import hash_password
from backend.app.core.rbac import SYSTEM_ROLES
from backend.app.db.models.user import Role, User
from backend.app.db.models.system_config import SystemConfig


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session_factory(test_engine):
    """Session factory bound to test engine."""
    factory = async_sessionmaker(
        bind=test_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    return factory


@pytest_asyncio.fixture(scope="function")
async def db_session(test_session_factory):
    """Yields a database session with seeded roles and initial state."""
    async with test_session_factory() as session:
        # Seed system roles
        for role_name, role_info in SYSTEM_ROLES.items():
            session.add(Role(
                name=role_name,
                description=role_info["description"],
                permissions=role_info["permissions"],
                is_system=role_info["is_system"],
            ))
        await session.commit()
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(test_engine, test_session_factory):
    """Async test client with active session factory binding."""
    session_module._engine = test_engine
    session_module._session_factory = test_session_factory

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
