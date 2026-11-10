# Implementation Plan: Data Center Monitoring Platform with 3D Floor Plan

**Document Version:** 1.3.0  
**Status:** Approved with Modifications (NPM, Frigate go2rtc, Mosquitto & Vite+TypeScript)  
**Target:** Foundation & Production-Ready System Blueprint  
**References:** `Task.md`, Deployment Architecture Corrections (2026-11-10)

---

## 1. Architecture Overview

### 1.1 High-Level System Architecture

The platform integrates directly with the existing server infrastructure (**Nginx Proxy Manager**, **Frigate with embedded go2rtc**, and an existing **Mosquitto MQTT broker**). The application repository ships only the core monitoring application and its database, avoiding redundant containers.

```
                             +----------------------------------------+
                             |              Client Browser            |
                             |  (Desktop, Tablet, Phone / PWA Ready)  |
                             +----------------------------------------+
                                   |                      |
                        HTTPS (REST/HTML/Assets)    WSS (Live Data / Events: /ws/live)
                                   |                      |
                                   v                      v
                             +----------------------------------------+
                             |     Existing Nginx Proxy Manager (NPM) |
                             |     - SSL / HTTP/2 Termination         |
                             |     - WebSockets Support: ENABLED (ON) |
                             +----------------------------------------+
                                   |
                         (Internal Docker / Host)
                                   |
                                   v
     +-------------------------------------------------------------------------+
     |                       server_monits_app (FastAPI)                       |
     |-------------------------------------------------------------------------|
     | - Auth & RBAC (Argon2 / Sessions / Double-submit CSRF / TOTP 2FA)       |
     | - DB-backed Rate Limiting & Lockout Tracker                             |
     | - Setup Wizard (403 Lockdown Post-Initialization)                       |
     | - External DB URL & Persistent Fernet Key Storage                       |
     | - Server-rendered Jinja2 UI + 3D Floor Plan Engine (Three.js)           |
     | - External MQTT Client (Auto-reconnect with backoff, UI status)         |
     | - Frigate Stream Gateway Client (Proxying streams to browser)           |
     +-------------------------------------------------------------------------+
            |                    |                           |
            v                    v                           v
     +-------------+    +------------------+        +--------------------+
     |  Database   |    | Existing External|        | Existing Frigate   |
     | (PostgreSQL |    | Mosquitto Broker |        | (go2rtc API :1984) |
     |  default;   |    | (Sensor Topics)  |        +--------------------+
     |  MySQL /    |    +------------------+                   ^
     |  MariaDB)   |                                           | RTSP / ONVIF
     +-------------+                                    +------------------+
            |                                           | Security Cameras |
            v                                           +------------------+
     +---------------+
     |  Redis Cache  | (Optional Compose Profile: with-redis)
     +---------------+
```

### 1.2 Component Breakdown & Refinements

1. **Backend Service (`backend/`)**:
   - **Framework**: Python 3.12, FastAPI, Uvicorn (ASGI).
   - **Database Layer**: SQLAlchemy 2.0 (AsyncIO), Alembic migrations. Cross-compatible dialect abstraction supporting **PostgreSQL (asyncpg)**, **MySQL (asyncmy)**, and **MariaDB (asyncmy)**. SQLite is strictly designated for local dev/testing (`APP_ENV=development`).
   - **Configuration Storage**: `DATABASE_URL` is **strictly stored outside the database** in the environment / `.env` file. The Fernet symmetric encryption key is generated once and persisted in the Docker volume (`/app/data/fernet.key`) and `.env`.
   - **Authentication, Sessions & Tokens**:
     - Argon2id password hashing with no hard-coded passwords.
     - State-managed server sessions and refresh tokens stored in `user_sessions` and `refresh_tokens`.
     - Login rate limiting and account lockout tracked directly in `login_attempts` table (DB-backed, multi-worker persistent).
     - CSRF protection for cookie-authenticated browser sessions using double-submit token verification.
     - Optional **TOTP 2FA** (RFC 6238) with 8 salted SHA-256 hashed single-use recovery backup codes.
   - **Lockdown on Setup**:
     - Setup endpoints (`/api/v1/setup/*`) return **403 Forbidden** once the system is initialized.
   - **Protected Metrics**:
     - `/metrics` is strictly restricted to authenticated users with the **Admin** role (or accessible over a dedicated internal port not exposed to NPM). Source IPs and `X-Forwarded-For` headers are never trusted.
   - **External MQTT Broker Client**:
     - Connects to the host's existing Mosquitto broker. Configurable in Admin UI (host, port, credentials encrypted at rest, TLS with optional CA cert, client ID, and live topic subscription test button).
     - Automated exponential backoff reconnection with live online/offline status reporting.
   - **Stream Gateway (Frigate Integration)**:
     - Connects to existing Frigate go2rtc base URL (`http://frigate:1984`), with a Test Connection button in the Admin UI.
     - Never exposes port 1984 to the internet; streams added through the API note that Frigate's `config.yml` is required for permanent retention across restarts.

2. **Frontend Architecture (`frontend/`)**:
   - **Build Tooling & Dev Server**: **Vite + TypeScript**. In local development, the Vite dev server (`http://localhost:5173`) proxies API calls (`/api`, `/ws`) to the FastAPI backend. For production, Vite bundles into static production assets served by FastAPI.
   - **3D Engine**: Three.js (targeting WebGL2 with WebGPU dynamic feature detection and graceful fallback).
   - **Styling**: Modern CSS3 with **Neon (dark)** and **Normal (light)** themes, responsive drawer/bottom sheet on smaller screens.
   - **Rendering Loop**: On-demand dirty flag pattern — re-renders only on user interaction, camera motion, hover, selection, or live telemetry data updates.

3. **Wi-Fi Survey Agent (`survey-agent/`)**:
   - Standalone portable Python CLI for Linux/macOS/Windows to record RSSI/BSSID measurements and transmit them to the backend API via scoped API tokens.

---

## 2. Directory & File Structure

```
Server_Monits/
├── .env.example                    # Template with DATABASE_URL, FERNET_KEY, MQTT & Frigate URLs
├── .gitignore
├── Dockerfile                      # Multi-stage production build (Frontend Vite build + Python App)
├── docker-compose.yml              # Production stack (App + Postgres + optional Redis)
├── docker-compose.dev.yml          # Development override
├── docker-compose.test-dbs.yml     # Dialect test harness (Postgres 16, MySQL 8.0, MariaDB 11.2)
├── README.md
├── Task.md
├── docs/
│   ├── PLAN.md                     # Master implementation plan
│   ├── DECISIONS.md                # Architectural decisions & deviations log
│   ├── API.md                      # Detailed API specification
│   └── DEPLOYMENT.md               # NPM setup, Mosquitto & Frigate integration guide
│
├── scripts/
│   └── server_verify.sh            # Dialect test runner (REQUIRE_REAL_DBS=1 against real containers)
│
├── frontend/                       # Vite + TypeScript + Three.js 3D Editor
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts              # Local dev server with proxy to backend :8000
│   ├── index.html
│   └── src/
│       ├── main.ts                 # Editor entry point
│       ├── core/
│       │   ├── engine.ts           # WebGL2/WebGPU renderer with on-demand dirty flag
│       │   ├── camera.ts           # Orbit 3D, Top-Down 2D, First-Person walkthrough
│       │   ├── grid.ts             # Metric grid, decimal snapping (0.05m, 0.1m, 0.5m, 1.0m)
│       │   └── theme.ts            # Neon (dark) vs Normal (light) themes
│       ├── editor/
│       │   ├── wall_builder.ts     # Wall drawing, room polygon closure, doors & windows
│       │   ├── object_manager.ts   # Placement, library, transform gizmo, collision detection
│       │   ├── history.ts          # 50-action Undo/Redo stack
│       │   └── touch.ts            # Touch gestures (pinch zoom, two-finger pan, orbit)
│       ├── ui/
│       │   ├── toolbar.ts          # Floating neon toolbar & camera mode switcher
│       │   ├── properties.ts       # Inspector drawer / bottom sheet for selected objects
│       │   └── stats_overlay.ts    # FPS counter & GPU renderer stats
│       └── api/
│           ├── client.ts           # REST API client with CSRF token injection
│           └── persistence.ts      # API sync + IndexedDB local draft backup
│
├── backend/
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/               # Migrations (0001_initial_schema, 0002_floor_plans_and_objects)
│   ├── app/
│   │   ├── main.py                 # FastAPI entrypoint, healthz, protected metrics, CSRF middleware
│   │   ├── api/
│   │   │   ├── deps.py             # Auth dependencies, DB session injection, permission guards
│   │   │   └── v1/
│   │   │       ├── api_router.py
│   │   │       ├── auth.py         # Login, session, refresh, CSRF, TOTP 2FA with hashed backup codes
│   │   │       ├── setup.py        # Setup wizard APIs (403 post-init; SQLite restricted to dev)
│   │   │       ├── users.py
│   │   │       ├── roles.py
│   │   │       ├── tokens.py
│   │   │       ├── audit.py
│   │   │       ├── floor_plans.py  # Plans, rooms, walls, decimal meters, JSON export/import
│   │   │       ├── settings.py     # System settings, MQTT config & test, Frigate gateway test
│   │   │       └── i18n.py
│   │   ├── core/
│   │   │   ├── config.py           # Settings, Fernet key volume persistence, env handling
│   │   │   ├── security.py         # Argon2id, JWT, Fernet encryption, TOTP, backup codes
│   │   │   ├── csrf.py             # Double-submit CSRF protection
│   │   │   ├── rbac.py             # Permissions & roles
│   │   │   ├── i18n.py             # Translation loader (en / id)
│   │   │   └── audit.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   └── models/
│   │   ├── services/
│   │   │   └── mqtt_service.py     # External MQTT subscriber with exponential backoff & status
│   │   ├── i18n/                   # en.json, id.json
│   │   ├── templates/              # Jinja2 views (base, setup, login, app, admin)
│   │   └── static/
│   │       ├── css/                # themes.css (neon vs light), main.css
│   │       ├── js/                 # Built JS assets (populated by Vite build or dev proxy)
│   │       └── vendor/             # Vendored Three.js modules
│   └── tests/
│       ├── test_auth.py
│       ├── test_rbac.py
│       ├── test_setup.py
│       ├── test_settings.py
│       ├── test_metrics_security.py# Strictly Admin-only verification for /metrics
│       ├── test_fernet_persistence.py
│       ├── test_sqlite_restriction.py
│       ├── test_db_dialects.py     # Skips without REQUIRE_REAL_DBS=1, fails on unreachable DB when set
│       ├── test_floor_plans.py     # Floor plan CRUD, JSON export/import & permissions
│       └── test_i18n.py
│
└── survey-agent/                   # Portable Wi-Fi survey utility
```

---

## 3. Comprehensive Database Schema

### 3.1 Entity Relationship Diagram

```
+--------------------+        +--------------------+        +---------------------+
|       users        |        |       roles        |        |     audit_logs      |
|--------------------|        |--------------------|        |---------------------|
| id (PK, String 36) |<------>| id (PK, String 36) |        | id (PK, String 36)  |
| username (Unique)  | N    M | name (Unique)      |        | user_id (FK->users) |
| email              |        | description        |        | action              |
| password_hash      |        | permissions (JSON) |        | resource_type       |
| is_active          |        | is_system          |        | resource_id         |
| is_totp_enabled    |        +--------------------+        | details (JSON)      |
| preferred_lang     |                                      | ip_address          |
| preferred_theme    |                                      | created_at (Index)  |
+--------------------+                                      +---------------------+
      |          |
      |          +----------------------+
      v                                 v
+------------------------+    +-----------------------+    +---------------------+
|     user_sessions      |    |    refresh_tokens     |    |     api_tokens      |
|------------------------|    |-----------------------|    |---------------------|
| id (PK, String 36)     |    | id (PK, String 36)    |    | id (PK, String 36)  |
| user_id (FK->users)    |    | user_id (FK->users)   |    | user_id (FK->users) |
| session_token (Index)  |    | token_hash (Index)    |    | token_hash (Index)  |
| ip_address             |    | expires_at            |    | name (label)        |
| user_agent             |    | revoked (Boolean)     |    | scopes (JSON)       |
| expires_at             |    | created_at            |    | expires_at          |
+------------------------+    +-----------------------+    | last_used_at        |
                                                           +---------------------+

+--------------------+        +--------------------+        +---------------------+
|    floor_plans     |        |       rooms        |        |   placed_objects    |
|--------------------|        |--------------------|        |---------------------|
| id (PK)            |<------>| id (PK)            |<------>| id (PK)             |
| name               | 1    N | floor_plan_id (FK) | 1    N | room_id (FK)        |
| site_name          |        | name               |        | object_type         |
| level_index        |        | polygon_points     |        | position_x, y, z    |
| grid_size_meters   |        | wall_height_m      |        | rotation_x, y, z    |
| scale_ratio        |        | wall_thickness_m   |        | scale_x, y, z       |
| metadata (JSON)    |        | color              |        | properties (JSON)   |
| created_at         |        +--------------------+        +---------------------+
+--------------------+

+--------------------+        +--------------------+        +---------------------+
|    data_sources    |        |      sensors       |        |  telemetry_readings |
|--------------------|        |--------------------|        |---------------------|
| id (PK)            |        | id (PK)            |        | id (BigInt, PK, AI) |
| name               |<------>| object_id (FK)     |<------>| sensor_id (FK, Idx) |
| type (mqtt/http/..) | 1    N | data_source_id(FK) | 1    N | timestamp (Idx)     |
| config (Encrypted) |        | metric_key         |        | temperature (°C)    |
| created_at         |        +--------------------+        | humidity (%RH)      |
+--------------------+                                      | raw_data (JSON)     |
                                                            +---------------------+
```

---

## 4. API Endpoints Specification

| Method | Endpoint | Access / Auth | Purpose |
|---|---|---|---|
| **Health & Metrics** | | | |
| `GET` | `/healthz` | Public | Liveness probe: checks DB connection |
| `GET` | `/metrics` | `Admin` Role Only | Prometheus metrics (never trusts source IP / X-Forwarded-For) |
| **Setup Wizard** | | | |
| `GET` | `/api/v1/setup/status` | Public | Check if system is initialized (403 if done) |
| `POST` | `/api/v1/setup/test-db` | Public | Test DB connection string (403 if done) |
| `POST` | `/api/v1/setup/migrate` | Public | Run database migrations (403 if done) |
| `POST` | `/api/v1/setup/admin` | Public | Create initial administrator user (403 if done) |
| **Authentication & Tokens** | | | |
| `GET` | `/api/v1/auth/csrf` | Public | Get fresh CSRF token |
| `POST` | `/api/v1/auth/login` | Public (Rate Limited) | Authenticate user, issue session cookie / JWT |
| `POST` | `/api/v1/auth/2fa/verify` | Public (Session Pending) | Verify TOTP code during 2FA login flow |
| `POST` | `/api/v1/auth/2fa/setup` | Authenticated | Generate TOTP secret & QR code |
| `POST` | `/api/v1/auth/2fa/confirm` | Authenticated | Confirm 2FA setup with first code |
| `POST` | `/api/v1/auth/logout` | Authenticated + CSRF | Invalidate session & tokens |
| `POST` | `/api/v1/auth/refresh` | Public (Refresh Token) | Rotate refresh token & issue new access token |
| `GET` | `/api/v1/auth/me` | Authenticated | Current user profile, roles, permissions |
| `PUT` | `/api/v1/auth/me` | Authenticated + CSRF | Update password, language, theme preference |
| **Floor Plans & 3D Objects** | | | |
| `GET` | `/api/v1/plans` | `plans:read` | List all floor plans |
| `POST` | `/api/v1/plans` | `plans:write` + CSRF | Create new floor plan |
| `GET` | `/api/v1/plans/{id}` | `plans:read` | Get complete floor plan with rooms & objects |
| `PUT` | `/api/v1/plans/{id}` | `plans:write` + CSRF | Update floor plan metadata, rooms & objects |
| `DELETE`| `/api/v1/plans/{id}` | `plans:write` + CSRF | Delete floor plan |
| `POST` | `/api/v1/plans/{id}/export` | `plans:read` | Export plan specification as JSON |
| `POST` | `/api/v1/plans/import` | `plans:write` + CSRF | Import plan specification from JSON |
| **Settings & External Integrations** | | | |
| `GET` | `/api/v1/settings` | `settings:read` | Get system settings & masked credentials |
| `PUT` | `/api/v1/settings` | `settings:write` + CSRF | Update settings (MQTT, Frigate, retention, theme) |
| `POST` | `/api/v1/settings/test-gateway` | `settings:read` | Test connection to Frigate go2rtc REST API |
| `POST` | `/api/v1/settings/test-mqtt` | `settings:read` | Test external Mosquitto connection & topic |
| `GET` | `/api/v1/settings/mqtt-status` | `settings:read` | Live MQTT connection status & statistics |
| `GET` | `/api/v1/i18n/{lang}` | Public | Load translation dictionary (en / id) |
| `WS` | `/ws/live` | Authenticated | Realtime telemetry, alerts, and access events |

---

## 5. Dialect Test Strategy (`test_db_dialects.py`)

1. **Docker Compose Test Harness (`docker-compose.test-dbs.yml`)**:
   - Spawns real instances of:
     - `postgres:16-alpine` (Port 5433:5432)
     - `mysql:8.0` (Port 3307:3306)
     - `mariadb:11.2` (Port 3308:3306)
2. **Execution & CI/CD Guard**:
   - `test_db_dialects.py` verifies connections, runs Alembic migrations, and performs schema CRUD.
   - **Requirement**: Unreachable database containers are skipped in local dev environments where Docker is absent, but **strictly fail** when `REQUIRE_REAL_DBS=1` is set (used by `scripts/server_verify.sh` on the server).

---

## 6. Frigate go2rtc Stream Gateway Integration

Rather than deploying a redundant media gateway container:
1. **Existing Infrastructure**: The server already operates Frigate with an embedded go2rtc instance on port 1984.
2. **Admin Gateway Setting**: The Admin UI allows configuring the go2rtc base URL (`http://frigate:1984`) with a live "Test Gateway" button that checks `/api/streams`.
3. **Camera Placement**: Cameras placed on the 3D floor plan reference existing stream names in Frigate (e.g. `rack_aisle_1`) or direct RTSP sources.
4. **Security Notice**: Port 1984 remains strictly internal to the Docker / LAN network and is never exposed to the public internet.

---

## 7. Phase Implementation Roadmap

- **Phase 1 (Complete)**: Core authentication, RBAC, setup wizard lockdown (403), database migrations, DB-backed rate limits, Fernet key persistence, TOTP 2FA with single-use backup codes, Admin-only `/metrics`, external MQTT broker service, and Frigate gateway configuration.
- **Phase 2 (Current)**: Interactive 3D floor plan editor (Vite + TypeScript + Three.js), real-world decimal meter scale, snapping, wall drawing, room polygon detection, door/window cutouts, 3D object manipulation, undo/redo, camera modes (orbit, 2D top-down, first-person), touch gestures, and JSON export/import.
- **Phase 3**: Thermohygrograph sensor integration, MQTT ingestion, 3D heatmaps (temperature & humidity) with IDW shader interpolation.
- **Phase 4**: Wi-Fi heatmap visualization and survey agent CLI.
- **Phase 5**: Server racks, 2D elevation canvas, U-slot component management, cable routing.
- **Phase 6**: Security cameras, go2rtc stream live viewing, access control door events.
- **Phase 7**: Production verification with `scripts/server_verify.sh`, backup/restore drills, and final release packaging.
