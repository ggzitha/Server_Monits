# Production Deployment Guide: Data Center 3D Monitoring Platform

This guide describes how to deploy the platform on your production server alongside existing infrastructure: **Nginx Proxy Manager (NPM)**, **Frigate** (with internal go2rtc), and an existing **Mosquitto MQTT broker**.

---

## 1. System Overview & Architecture Integration

```
                         [ Public Internet ]
                                 |
                                 v
                +---------------------------------+
                |   Nginx Proxy Manager (NPM)     |
                |   - SSL / Let's Encrypt         |
                |   - WebSockets Support: ON      |
                +---------------------------------+
                                 |
                     (Shared Docker Network)
                                 |
                                 v
                +---------------------------------+
                |   server_monits_app (:8000)     |
                |   FastAPI + 3D Floor Plan App   |
                +---------------------------------+
                     |            |            |
                     |            |            +-----------------------+
                     v            v                                    v
     +-----------------+   +-----------------------------+   +-------------------+
     | server_monits_db|   | Existing Mosquitto Broker   |   | Existing Frigate  |
     | (PostgreSQL 16) |   | (Sensor telemetry topics)   |   | (go2rtc API :1984)|
     +-----------------+   +-----------------------------+   +-------------------+
```

- **App & Database**: Shipped as clean, minimal containers (`app` + `db`).
- **Reverse Proxy**: Handled externally by your existing **Nginx Proxy Manager (NPM)**.
- **Video Streaming**: Provided by your existing **Frigate** instance (embedded go2rtc API).
- **Sensor Ingestion**: Delivered from your existing **Mosquitto MQTT broker**.

---

## 2. Nginx Proxy Manager (NPM) Configuration

### 2.1 Recommended Default: Option A (Shared Docker Network)

For maximum isolation and security, the app container does not publish ports directly to the host. Instead, connect NPM and `server_monits_app` to a shared Docker bridge network.

1. **Connect NPM to shared network** (if not already done):
   ```bash
   # Create a shared network if needed:
   docker network create npm_net

   # Connect your existing NPM container:
   docker network connect npm_net nginx-proxy-manager
   ```

2. **In `docker-compose.override.yml` (or `docker-compose.yml`)**:
   Add the external network:
   ```yaml
   networks:
     monits_net:
       driver: bridge
     npm_net:
       external: true

   services:
     app:
       networks:
         - monits_net
         - npm_net
   ```

3. **In the NPM Web Admin (`http://your-server-ip:81`)**:
   - Click **Hosts** > **Proxy Hosts** > **Add Proxy Host**.
   - **Details Tab**:
     - **Domain Names**: `monits.yourdomain.com`
     - **Scheme**: `http`
     - **Forward Hostname / IP**: `server_monits_app` (resolves cleanly across the Docker network)
     - **Forward Port**: `8000`
     - **Block Common Exploits**: **ON**
     - **Websockets Support**: **MUST BE ENABLED (ON)**
       > [!IMPORTANT]
       > Websockets Support is required for `/ws/live`. If disabled, live telemetry updates, alerts, and access events will not reach client browsers.
   - **SSL Tab**:
     - Select your SSL certificate or generate a new Let's Encrypt certificate.
     - **Force SSL**: **ON**
     - **HTTP/2 Support**: **ON**
     - **HSTS Enabled**: **ON**
   - Click **Save**.

### 2.2 Alternative: Option B (Host Port Forwarding)
If your NPM container is configured to forward directly to host ports:
1. Publish port `8000` in `docker-compose.yml`:
   ```yaml
   services:
     app:
       ports:
         - "127.0.0.1:8000:8000"
   ```
2. In NPM, set **Forward Hostname / IP** to `172.17.0.1`, `host.docker.internal`, or your server's LAN IP, with port `8000`.

---

## 3. Existing Mosquitto MQTT Broker Integration

The platform connects to your existing Mosquitto broker as an external data source.

### 3.1 Create a Dedicated Read-Only Mosquitto User
For security, create a dedicated user restricted to sensor topics:

```bash
# 1. Create user with secure password
sudo mosquitto_passwd -b /etc/mosquitto/passwd monits_reader <YOUR_SECURE_PASSWORD>

# 2. Grant read-only access to sensor topics in /etc/mosquitto/acl:
# user monits_reader
# topic read sensors/#
# topic read datacenter/#

# 3. Reload Mosquitto
sudo systemctl reload mosquitto
```

### 3.2 Network Host Selection
- **If Mosquitto runs in Docker**: Connect via container name (e.g., `mosquitto`) on the same Docker network.
- **If Mosquitto runs on host or LAN**: Use the server's LAN IP (e.g. `192.168.1.10`) or `host.docker.internal` / `172.17.0.1`.

### 3.3 Configure in Admin UI or Environment
In the platform web interface:
1. Navigate to **Admin > Settings > External Mosquitto MQTT Broker**.
2. Enter host, port (default `1883`), username (`monits_reader`), and password.
3. Passwords are encrypted at rest using the persistent Fernet key.
4. Click **Test Subscription**: Enter a topic (e.g. `sensors/#`) to verify live subscription and inspect incoming payloads.
5. Live online/offline status displays with automatic backoff reconnection.

---

## 4. Existing Frigate (go2rtc) Stream Gateway Integration

The platform integrates with your existing Frigate installation to stream CCTV cameras directly to web browsers via WebRTC / MSE / HLS.

### 4.1 Base URL Configuration
1. In the platform web interface, navigate to **Admin > Settings > Stream Gateway**.
2. Set **Gateway Base URL** to your Frigate instance's internal go2rtc address:
   - Example (shared Docker network): `http://frigate:1984`
   - Example (LAN address): `http://192.168.1.50:1984`
3. Click **Test Gateway Connection** to verify API responsiveness and view active streams.

### 4.2 Stream Mapping in 3D Scene
When placing a CCTV camera on the 3D floor plan:
- Reference an existing stream defined in Frigate (e.g., `front_door`, `server_aisle_1`).
- Or specify a direct RTSP / ONVIF / HTTP URL.

> [!CAUTION]
> **Security Notice**:
> Frigate's go2rtc management API (port 1984) provides direct stream control and **must NEVER be exposed to the public internet**. Only internal network access from `server_monits_app` should reach this port.

> [!NOTE]
> **Stream Persistence**:
> Streams added dynamically via the go2rtc REST API are kept in memory and may not persist across Frigate container restarts. For permanent camera streams, define them in Frigate's permanent `config.yml`.

---

## 5. Deployment Steps

### Step 1: Clone Repository & Setup Environment
```bash
git clone <repo-url> /opt/server-monits
cd /opt/server-monits
cp .env.example .env
```

### Step 2: Configure Environment
Edit `.env`:
- `SECRET_KEY`: Set a secure random 32+ byte string.
- `DATABASE_URL`: Defaults to the internal PostgreSQL container.
- `ADMIN_PASSWORD`: (Optional) Leave empty to set during browser wizard, or set here for headless setup.
- `GO2RTC_API_URL`: Set to your Frigate address (e.g., `http://frigate:1984`).

### Step 3: Launch Containers
```bash
docker compose up -d --build
```

### Step 4: First-Run Setup Wizard
1. Open the domain configured in NPM (e.g. `https://monits.yourdomain.com`).
2. Follow the setup wizard:
   - Test database connection.
   - Run migrations.
   - Choose a strong administrator password.
   - Pick default language (English or Indonesian) and theme (Neon dark or Normal light).
3. Upon completion, setup endpoints are permanently locked with `403 Forbidden`.

---

## 6. Backup & Restore (Database & Fernet Key)

> [!IMPORTANT]
> The **Fernet key (`fernet.key`)** encrypts all sensitive credentials at rest (MQTT password, sensor API secrets, camera passwords). **You MUST back up the Fernet key together with the database.** Restoring a database dump without the matching `fernet.key` renders all stored secrets permanently unreadable.

### 6.1 Unified Backup Procedure
```bash
BACKUP_DATE=$(date +%F_%H%M%S)

# 1. Backup PostgreSQL database
docker exec -t server_monits_db pg_dump -U postgres server_monits | gzip > "backup_db_${BACKUP_DATE}.sql.gz"

# 2. Backup persistent Fernet key from the app data volume
docker cp server_monits_app:/app/data/fernet.key "./backup_fernet_${BACKUP_DATE}.key"

# 3. Secure the backup files (restrict permissions)
chmod 600 "backup_fernet_${BACKUP_DATE}.key" "backup_db_${BACKUP_DATE}.sql.gz"
echo "Backup complete: backup_db_${BACKUP_DATE}.sql.gz and backup_fernet_${BACKUP_DATE}.key"
```

### 6.2 Unified Restore Procedure
```bash
RESTORE_DATE="2026-11-10_120000"

# 1. Restore Fernet encryption key to container volume first
docker cp "./backup_fernet_${RESTORE_DATE}.key" server_monits_app:/app/data/fernet.key

# 2. Restore PostgreSQL database
gunzip < "backup_db_${RESTORE_DATE}.sql.gz" | docker exec -i server_monits_db psql -U postgres -d server_monits

# 3. Restart app container to reload restored encryption cipher
docker compose restart app
```

---

## 7. Dialect & Production Stack Verification Script (`scripts/server_verify.sh`)

To test migrations and CRUD operations against real PostgreSQL 16, MySQL 8.0, and MariaDB 11.2 containers, and verify the production container stack before rolling out updates:

```bash
chmod +x scripts/server_verify.sh
./scripts/server_verify.sh
```

This automated verification:
1. Launches `docker-compose.test-dbs.yml` containers (PostgreSQL 16, MySQL 8.0, MariaDB 11.2).
2. Waits until each database port is healthy.
3. Sets `REQUIRE_REAL_DBS=1` and runs `pytest backend/tests/test_db_dialects.py` to ensure schema migrations and CRUD pass across all dialects.
4. Builds and launches the real production stack (`docker compose up -d --build` for `app` + `db`).
5. Validates that `/healthz` returns `{"status": "healthy", "database": "connected"}`.
6. Prints a consolidated pass/fail summary and performs zero-residue cleanup on exit.
