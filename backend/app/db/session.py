import logging
from typing import AsyncGenerator, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from backend.app.core.config import settings

logger = logging.getLogger("server_monits.db")

# Global engine and sessionmaker references
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def normalize_db_url(url: str) -> str:
    """Ensure database URL has the correct async dialect prefix."""
    url = url.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("mysql://") and not url.startswith("mysql+asyncmy://"):
        url = url.replace("mysql://", "mysql+asyncmy://", 1)
    elif url.startswith("mariadb://") and not url.startswith("mysql+asyncmy://"):
        url = url.replace("mariadb://", "mysql+asyncmy://", 1)
    elif url.startswith("sqlite:///") and not url.startswith("sqlite+aiosqlite:///"):
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


def get_engine() -> Optional[AsyncEngine]:
    """Get or create the global async engine."""
    global _engine, _session_factory
    if _engine is not None:
        return _engine
    
    db_url = settings.DATABASE_URL
    if not db_url:
        return None

    norm_url = normalize_db_url(db_url)
    connect_args = {}
    if norm_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    _engine = create_async_engine(
        norm_url,
        echo=settings.DEBUG,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    _session_factory = async_sessionmaker(
        bind=_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    return _engine


def get_session_factory() -> Optional[async_sessionmaker[AsyncSession]]:
    """Get the active async session factory, initializing engine if needed."""
    global _session_factory
    if _session_factory is None:
        get_engine()
    return _session_factory


def set_engine_url(new_url: str) -> AsyncEngine:
    """Reconfigure engine with a new connection URL (used by Setup Wizard)."""
    global _engine, _session_factory
    if _engine is not None:
        # Note: Dispose is sync in newer SQLAlchemy for async engine wrapper
        try:
            _engine.sync_engine.dispose()
        except Exception:
            pass
            
    norm_url = normalize_db_url(new_url)
    connect_args = {}
    if norm_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    _engine = create_async_engine(
        norm_url,
        echo=settings.DEBUG,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    _session_factory = async_sessionmaker(
        bind=_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    return _engine


def get_session_factory() -> Optional[async_sessionmaker[AsyncSession]]:
    """Get the active async session factory, initializing engine if needed."""
    global _session_factory
    if _session_factory is None:
        get_engine()
    return _session_factory


async def test_database_connection(url: str) -> Tuple[bool, str]:
    """Test connection to a target database URL by executing SELECT 1."""
    norm_url = normalize_db_url(url)
    connect_args = {}
    if norm_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    test_engine = None
    try:
        test_engine = create_async_engine(
            norm_url,
            echo=False,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        async with test_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, "Connection successful"
    except Exception as e:
        return False, str(e)
    finally:
        if test_engine is not None:
            try:
                await test_engine.dispose()
            except Exception:
                pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    engine = get_engine()
    if engine is None or _session_factory is None:
        raise RuntimeError("Database is not configured yet. Please complete the setup wizard.")
        
    async with _session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

