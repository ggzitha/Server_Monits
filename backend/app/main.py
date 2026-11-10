import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Request, Response, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text

from backend.app.api.deps import (
    get_current_user_optional,
    is_system_initialized,
    verify_metrics_access,
)
from backend.app.api.v1.api_router import api_router
from backend.app.core.config import settings
from backend.app.core.csrf import validate_csrf_token, generate_csrf_token
from backend.app.core.i18n import create_i18n_helper, load_translations
from backend.app.core.rbac import SYSTEM_ROLES
from backend.app.core.security import hash_password
from backend.app.db.base import Base
from backend.app.db.models.system_config import SystemConfig
from backend.app.db.models.user import Role, User
from backend.app.db.session import get_engine, test_database_connection

logger = logging.getLogger("server_monits")
logging.basicConfig(level=logging.INFO if not settings.DEBUG else logging.DEBUG)

APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


async def auto_initialize_from_env():
    """Perform automatic headless setup if DATABASE_URL and ADMIN_PASSWORD are set in environment and DB uninitialized."""
    if not settings.DATABASE_URL or not settings.ADMIN_PASSWORD:
        return

    engine = get_engine()
    if engine is None:
        return

    try:
        from backend.app.db.session import _session_factory
        if _session_factory is None:
            return

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with _session_factory() as session:
            initialized = await is_system_initialized(session)
            if initialized:
                return

            logger.info("Auto-initializing platform from environment variables...")
            # Seed roles
            for role_name, role_info in SYSTEM_ROLES.items():
                res = await session.execute(select(Role).where(Role.name == role_name))
                if not res.scalar_one_or_none():
                    session.add(Role(
                        name=role_name,
                        description=role_info["description"],
                        permissions=role_info["permissions"],
                        is_system=role_info["is_system"],
                    ))
            await session.flush()

            # Seed Admin
            admin_role = (await session.execute(select(Role).where(Role.name == "Admin"))).scalar_one()
            admin_user = (await session.execute(select(User).where(User.username == settings.ADMIN_USERNAME))).scalar_one_or_none()
            if not admin_user:
                admin_user = User(
                    username=settings.ADMIN_USERNAME,
                    email=settings.ADMIN_EMAIL,
                    password_hash=hash_password(settings.ADMIN_PASSWORD),
                    preferred_lang=settings.DEFAULT_LANGUAGE,
                    preferred_theme=settings.DEFAULT_THEME,
                    is_active=True,
                )
                admin_user.roles.append(admin_role)
                session.add(admin_user)

            # System Config
            cfgs = {
                "is_initialized": "true",
                "default_language": settings.DEFAULT_LANGUAGE,
                "default_theme": settings.DEFAULT_THEME,
                "telemetry_retention_days": str(settings.TELEMETRY_RETENTION_DAYS),
            }
            for k, v in cfgs.items():
                existing = (await session.execute(select(SystemConfig).where(SystemConfig.key == k))).scalar_one_or_none()
                if existing:
                    existing.value = v
                else:
                    session.add(SystemConfig(key=k, value=v))

            await session.commit()
            logger.info("Auto-initialization completed successfully.")
    except Exception as e:
        logger.warning(f"Auto-initialization check skipped or failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup & shutdown events."""
    load_translations()
    await auto_initialize_from_env()
    yield
    # Shutdown
    engine = get_engine()
    if engine:
        try:
            await engine.dispose()
        except Exception:
            pass


app = FastAPI(
    title=settings.APP_NAME,
    description="Data Center 3D Floor Plan & Monitoring Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    """Enforce CSRF double-submit token verification on mutating requests."""
    try:
        validate_csrf_token(request)
    except HTTPException as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
        
    response = await call_next(request)
    return response


# Mount Static Files
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount API Router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


# --- Health & Metrics Endpoints ---

@app.get("/healthz", tags=["monitoring"])
async def healthz():
    """Liveness probe: verifies database connectivity and core system state."""
    db_status = "not_configured"
    engine = get_engine()
    if engine is not None:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception as e:
            db_status = f"unhealthy: {e}"

    return {
        "status": "healthy" if db_status in ("connected", "not_configured") else "degraded",
        "database": db_status,
        "app_env": settings.APP_ENV,
        "timestamp": int(time.time()),
    }


@app.get("/metrics", dependencies=[Depends(verify_metrics_access)], tags=["monitoring"])
async def metrics(request: Request):
    """Prometheus metrics endpoint. Strictly protected (Admin role only). Never trusts source IP or X-Forwarded-For."""
    lines = [
        "# HELP server_monits_up Server operational status",
        "# TYPE server_monits_up gauge",
        "server_monits_up 1",
        "# HELP server_monits_retention_days Configured telemetry retention days",
        "# TYPE server_monits_retention_days gauge",
        f"server_monits_retention_days {settings.TELEMETRY_RETENTION_DAYS}",
    ]
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


# --- WebSocket Live Streaming & Telemetry Hub ---

class LiveConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

live_ws_manager = LiveConnectionManager()


@app.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    """Realtime WebSocket telemetry, notifications, and pulse updates."""
    await live_ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Respond to client heartbeats
            await websocket.send_json({"type": "pong", "timestamp": int(time.time())})
    except WebSocketDisconnect:
        live_ws_manager.disconnect(websocket)
    except Exception:
        live_ws_manager.disconnect(websocket)


# --- UI Pages & Template Context Helpers ---

def get_template_context(request: Request, current_user: Optional[User] = None) -> dict:
    """Prepare context variables for Jinja2 templates (i18n, theme, user, csrf)."""
    user_lang = request.cookies.get("monit_lang")
    user_theme = request.cookies.get("monit_theme")

    if current_user:
        user_lang = user_lang or current_user.preferred_lang
        user_theme = user_theme or current_user.preferred_theme

    user_lang = user_lang if user_lang in ("en", "id") else settings.DEFAULT_LANGUAGE
    user_theme = user_theme if user_theme in ("neon", "light") else settings.DEFAULT_THEME

    csrf_token = request.cookies.get(settings.CSRF_COOKIE_NAME, "")
    if not csrf_token:
        csrf_token = generate_csrf_token()

    return {
        "request": request,
        "current_user": current_user,
        "current_lang": user_lang,
        "current_theme": user_theme,
        "csrf_token": csrf_token,
        "debug": settings.DEBUG,
        "_": create_i18n_helper(user_lang),
    }


@app.get("/", response_class=HTMLResponse)
async def page_dashboard(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Main 3D floor plan dashboard."""
    # Check if setup needed
    from backend.app.db.session import _session_factory
    if _session_factory is not None:
        async with _session_factory() as session:
            if not await is_system_initialized(session):
                return RedirectResponse(url="/setup", status_code=302)

    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    ctx = get_template_context(request, current_user)
    ctx["active_tab"] = "dashboard"
    return templates.TemplateResponse(request=request, name="app.html", context=ctx)


@app.get("/setup", response_class=HTMLResponse)
async def page_setup(request: Request):
    """First-run setup wizard. Redirects away if already initialized."""
    from backend.app.db.session import _session_factory
    if _session_factory is not None:
        try:
            async with _session_factory() as session:
                if await is_system_initialized(session):
                    return RedirectResponse(url="/login", status_code=302)
        except Exception:
            pass

    ctx = get_template_context(request, None)
    ctx["show_nav"] = False
    return templates.TemplateResponse(request=request, name="setup.html", context=ctx)


@app.get("/login", response_class=HTMLResponse)
async def page_login(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """User authentication page."""
    if current_user:
        return RedirectResponse(url="/", status_code=302)

    ctx = get_template_context(request, None)
    ctx["show_nav"] = False
    return templates.TemplateResponse(request=request, name="login.html", context=ctx)


@app.get("/admin/users", response_class=HTMLResponse)
async def page_admin_users(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Admin user management page."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    ctx = get_template_context(request, current_user)
    ctx["active_tab"] = "users"
    return templates.TemplateResponse(request=request, name="admin/users.html", context=ctx)


@app.get("/admin/settings", response_class=HTMLResponse)
async def page_admin_settings(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Admin system settings page."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    ctx = get_template_context(request, current_user)
    ctx["active_tab"] = "settings"
    return templates.TemplateResponse(request=request, name="admin/settings.html", context=ctx)


@app.get("/admin/audit", response_class=HTMLResponse)
async def page_admin_audit(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Audit logs page."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    ctx = get_template_context(request, current_user)
    ctx["active_tab"] = "audit"
    return templates.TemplateResponse(request=request, name="admin/audit.html", context=ctx)

