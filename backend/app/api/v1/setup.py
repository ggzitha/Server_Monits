from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import require_uninitialized, is_system_initialized
from backend.app.core.config import settings, persist_env_variable, get_or_generate_fernet_key
from backend.app.core.rbac import SYSTEM_ROLES
from backend.app.core.security import hash_password
from backend.app.db.base import Base
from backend.app.db.models.system_config import SystemConfig
from backend.app.db.models.user import Role, User
from backend.app.db.session import (
    get_db,
    get_engine,
    set_engine_url,
    test_database_connection,
)

router = APIRouter(prefix="/setup", tags=["setup"])


class TestDbRequest(BaseModel):
    db_type: str = Field(..., description="postgresql, mysql, mariadb, or sqlite")
    host: Optional[str] = "localhost"
    port: Optional[int] = 5432
    db_name: str = "server_monits"
    username: Optional[str] = "postgres"
    password: Optional[str] = "postgres"
    custom_url: Optional[str] = None


class InitializeRequest(BaseModel):
    db_type: str = "postgresql"
    host: Optional[str] = "localhost"
    port: Optional[int] = 5432
    db_name: str = "server_monits"
    username: Optional[str] = "postgres"
    password: Optional[str] = "postgres"
    custom_url: Optional[str] = None
    
    admin_username: str = "admin"
    admin_password: str = Field(..., min_length=8, description="Initial administrator password (min 8 chars)")
    admin_email: str = "admin@datacenter.internal"
    
    default_language: str = "en"
    default_theme: str = "neon"


def build_connection_url(req: TestDbRequest | InitializeRequest) -> str:
    """Build async database URL from request parameters."""
    if req.custom_url:
        return req.custom_url.strip()

    db_type = req.db_type.lower()
    if db_type == "postgresql":
        return f"postgresql+asyncpg://{req.username}:{req.password}@{req.host}:{req.port}/{req.db_name}"
    elif db_type in ("mysql", "mariadb"):
        return f"mysql+asyncmy://{req.username}:{req.password}@{req.host}:{req.port}/{req.db_name}"
    elif db_type == "sqlite":
        from pathlib import Path
        Path("./data").mkdir(parents=True, exist_ok=True)
        if req.db_name == ":memory:":
            return "sqlite+aiosqlite:///:memory:"
        return f"sqlite+aiosqlite:///./data/{req.db_name}.db"
    else:
        raise ValueError(f"Unsupported database type: {req.db_type}")


@router.get("/status")
async def get_setup_status():
    """Check if the system setup has been completed."""
    engine = get_engine()
    if engine is None:
        return {"is_initialized": False, "has_db": False}
    
    try:
        from backend.app.db.session import _session_factory
        if _session_factory is None:
            return {"is_initialized": False, "has_db": False}
        async with _session_factory() as session:
            initialized = await is_system_initialized(session)
            return {"is_initialized": initialized, "has_db": True}
    except Exception:
        return {"is_initialized": False, "has_db": False}


@router.post("/test-db", dependencies=[Depends(require_uninitialized)])
async def test_db_endpoint(req: TestDbRequest):
    """Test connection to the specified database configuration."""
    if req.db_type.lower() == "sqlite" and settings.APP_ENV == "production" and not settings.DEBUG:
        raise HTTPException(
            status_code=400,
            detail="SQLite is restricted to development and testing environments only. Please select PostgreSQL, MySQL, or MariaDB."
        )
    try:
        url = build_connection_url(req)
        success, message = await test_database_connection(url)
        return {"success": success, "message": message, "url_masked": url.split("@")[-1] if "@" in url else url}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/initialize", dependencies=[Depends(require_uninitialized)])
async def initialize_system(req: InitializeRequest):
    """Run migrations, seed roles and admin account, and persist configuration."""
    if req.db_type.lower() == "sqlite" and settings.APP_ENV == "production" and not settings.DEBUG:
        raise HTTPException(
            status_code=400,
            detail="SQLite is restricted to development and testing environments only. Please select PostgreSQL, MySQL, or MariaDB."
        )
    if not req.admin_password or len(req.admin_password.strip()) < 8:
        raise HTTPException(
            status_code=400,
            detail="Administrator password is required and must be at least 8 characters."
        )
    try:
        target_url = build_connection_url(req)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    # Test connection first
    success, msg = await test_database_connection(target_url)
    if not success:
        raise HTTPException(status_code=400, detail=f"Database connection failed: {msg}")

    # 1. Persist DATABASE_URL to external .env file
    persist_env_variable("DATABASE_URL", target_url)
    settings.DATABASE_URL = target_url

    # 2. Persist Fernet key if not already set
    if not settings.FERNET_KEY:
        settings.FERNET_KEY = get_or_generate_fernet_key()

    # 3. Reconfigure active database engine
    engine = set_engine_url(target_url)

    # 4. Create all database tables (schema migration)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 5. Populate initial system roles, admin user, and preferences
    from backend.app.db.session import _session_factory
    if _session_factory is None:
        raise HTTPException(status_code=500, detail="Failed to initialize session factory")

    async with _session_factory() as session:
        # Seed system roles
        for role_name, role_info in SYSTEM_ROLES.items():
            role_stmt = select(Role).where(Role.name == role_name)
            res = await session.execute(role_stmt)
            existing_role = res.scalar_one_or_none()
            if not existing_role:
                new_role = Role(
                    name=role_name,
                    description=role_info["description"],
                    permissions=role_info["permissions"],
                    is_system=role_info["is_system"],
                )
                session.add(new_role)
        
        await session.flush()

        # Seed initial admin user
        admin_role_stmt = select(Role).where(Role.name == "Admin")
        admin_role_res = await session.execute(admin_role_stmt)
        admin_role = admin_role_res.scalar_one()

        user_stmt = select(User).where(User.username == req.admin_username)
        user_res = await session.execute(user_stmt)
        admin_user = user_res.scalar_one_or_none()

        if not admin_user:
            admin_user = User(
                username=req.admin_username,
                email=req.admin_email,
                password_hash=hash_password(req.admin_password),
                is_active=True,
                preferred_lang=req.default_language,
                preferred_theme=req.default_theme,
            )
            admin_user.roles.append(admin_role)
            session.add(admin_user)
        else:
            admin_user.password_hash = hash_password(req.admin_password)
            if admin_role not in admin_user.roles:
                admin_user.roles.append(admin_role)

        # Mark system initialized in system_config
        configs = {
            "is_initialized": "true",
            "default_language": req.default_language,
            "default_theme": req.default_theme,
            "telemetry_retention_days": str(settings.TELEMETRY_RETENTION_DAYS),
        }
        for k, v in configs.items():
            cfg_stmt = select(SystemConfig).where(SystemConfig.key == k)
            cfg_res = await session.execute(cfg_stmt)
            existing_cfg = cfg_res.scalar_one_or_none()
            if existing_cfg:
                existing_cfg.value = v
            else:
                session.add(SystemConfig(key=k, value=v))

        await session.commit()

    return {
        "success": True,
        "message": "System successfully initialized. Setup is now locked.",
        "admin_username": req.admin_username,
    }
