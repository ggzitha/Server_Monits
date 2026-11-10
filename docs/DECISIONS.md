# Architectural Decisions Log

This document records key technical decisions, trade-offs, and deviations from early specifications.

---

## Decision 1: UI Architecture (Python Web App + Vite/Three.js)
- **Context:** `Task.md` Section 2 clarified that browsers cannot execute Python to render 3D scenes.
- **Decision:** Use FastAPI to serve the base HTML and manage server-side concerns (session auth, i18n, setup wizard, admin panels), while interactive 3D rendering and client widgets are authored in TypeScript/modern ES Modules using Three.js (targeting WebGL2 with WebGPU dynamic fallback).

---

## Decision 2: External Storage for Database Connection & Persistent Fernet Key
- **Context:** The database connection cannot be stored inside the database it connects to. In addition, secrets at rest (camera passwords, tokens, MQTT credentials) require symmetric encryption.
- **Decision:**
  - Store the chosen `DATABASE_URL` in `.env` (or environment variables) outside the database.
  - The setup wizard writes the configured database URL and generates a permanent Fernet encryption key once, persisting it on the Docker named volume (`/app/data/fernet.key`) and `.env`. The key is never regenerated on container restarts.

---

## Decision 3: Setup Wizard 403 Lockdown Post-Initialization
- **Context:** Once the initial admin and database are configured, setup endpoints (`/api/v1/setup/*`) must be strictly inaccessible to prevent unauthorized re-initialization.
- **Decision:** The setup router enforces a middleware/dependency check that queries the initialization status; once initialized, any access to `/api/v1/setup/*` immediately returns `HTTP 403 Forbidden`.

---

## Decision 4: Protected Metrics Endpoint (`/metrics`)
- **Context:** Operational Prometheus metrics may leak internal operational details if made publicly available. In reverse-proxied environments (like Nginx Proxy Manager), relying on client source IP or `X-Forwarded-For` headers is insecure and subject to header spoofing.
- **Decision:** Access to `/metrics` is strictly restricted to authenticated users with the `Admin` role (or accessible on a separate internal metrics port not exposed via NPM). Source IP addresses and `X-Forwarded-For` headers are never trusted. All unauthenticated or non-admin requests receive `HTTP 403 Forbidden`.

---

## Decision 5: Session & Token Architecture + CSRF Protection + TOTP 2FA
- **Context:** Supporting both browser users (interactive 3D floor plan, admin panels) and headless agents (Wi-Fi survey agent, IoT gateway) with strong security.
- **Decision:**
  - **Browser Users:** State-managed server sessions stored in `user_sessions`, authenticated via HTTP-only secure cookies with double-submit `X-CSRF-Token` validation on all mutating requests.
  - **Optional 2FA:** RFC 6238 TOTP with QR code setup and 8 salted SHA-256 hashed single-use recovery backup codes.
  - **Headless Agents & CLI:** Scoped API tokens (`api_tokens` table) sent as Bearer tokens, bypassing CSRF checks.

---

## Decision 6: Telemetry Data High-Volume Optimization
- **Context:** Sensor readings (temperature, humidity) will accumulate thousands of rows per hour.
- **Decision:**
  - `telemetry_readings` uses a 64-bit `BigInteger` autoincrement primary key (with `Integer` variant for SQLite ROWID compatibility) to avoid 32-bit integer overflow.
  - Composite index `(sensor_id, timestamp)` for query performance when rendering sparklines and calculating room heatmaps.
  - Retention threshold (e.g. 90 days) configurable in `system_config` with an automated cleanup job.

---

## Decision 7: External Nginx Proxy Manager, Frigate (go2rtc), and Mosquitto Integration
- **Context:** The production host server already operates **Nginx Proxy Manager (NPM)**, **Frigate** (with embedded go2rtc), and a **Mosquitto** MQTT broker.
- **Decision:**
  - Do NOT ship bundled reverse proxy (Traefik/Nginx) or media gateway (go2rtc) containers.
  - `docker-compose.yml` strictly contains only the `app`, the `database` (PostgreSQL 16 default), and optional `redis`.
  - The app container does not publish host ports by default; Nginx Proxy Manager routes to it over Docker networking (with Websockets Support enabled for `/ws/live`).
  - The Admin UI provides settings to connect to the existing Frigate go2rtc base URL (`http://frigate:1984`), with a Test button and security notice that port 1984 must never be public.
  - The Admin UI provides settings to connect to the existing Mosquitto broker (host, port, credentials encrypted at rest, TLS, client ID, and live topic subscription test), with automatic reconnection backoff and online/offline status display.
