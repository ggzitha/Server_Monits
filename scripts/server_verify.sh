#!/usr/bin/env bash
# ==============================================================================
# server_verify.sh - Production Server Database Dialect & Stack Verification
# 1. Tests PostgreSQL 16, MySQL 8.0, and MariaDB 11.2 containers (REQUIRE_REAL_DBS=1)
# 2. Builds and starts real production stack (app + db) and validates /healthz
# 3. Formats a clear pass/fail summary and cleans up on exit
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

echo "===================================================================="
echo "          Server_Monits: Production Stack Verification              "
echo "===================================================================="

DIALECT_COMPOSE="docker-compose.test-dbs.yml"
STACK_COMPOSE="docker-compose.yml"

cleanup() {
    echo ""
    echo ">> [Cleanup] Shutting down verification containers and cleaning volumes..."
    docker compose -f "${DIALECT_COMPOSE}" down -v --remove-orphans > /dev/null 2>&1 || true
    docker compose -f "${STACK_COMPOSE}" down -v --remove-orphans > /dev/null 2>&1 || true
    echo ">> [Cleanup] Complete."
}

trap cleanup EXIT

# ------------------------------------------------------------------------------
# STEP 1: Dialect Test Suite against real PostgreSQL, MySQL, and MariaDB
# ------------------------------------------------------------------------------
echo ">> Step 1: Starting PostgreSQL, MySQL, and MariaDB dialect test containers..."
docker compose -f "${DIALECT_COMPOSE}" up -d --remove-orphans

echo ">> Step 2: Waiting for database dialect engines to become healthy..."
MAX_WAIT=45

wait_for_port() {
    local host="127.0.0.1"
    local port="$1"
    local name="$2"
    local count=0
    while ! nc -z "${host}" "${port}" >/dev/null 2>&1; do
        sleep 1
        count=$((count + 1))
        if [ ${count} -ge ${MAX_WAIT} ]; then
            echo "ERROR: Timed out waiting for ${name} on port ${port}!"
            exit 1
        fi
    done
    echo "   ✓ ${name} is reachable on port ${port}"
}

wait_for_port 5433 "PostgreSQL 16"
wait_for_port 3307 "MySQL 8.0"
wait_for_port 3308 "MariaDB 11.2"

echo ">> Stabilizing container daemon connections..."
sleep 5

echo ">> Step 3: Executing multi-dialect migration and CRUD test suite (REQUIRE_REAL_DBS=1)..."
export REQUIRE_REAL_DBS=1

DIALECT_EXIT_CODE=0
pytest backend/tests/test_db_dialects.py -v || DIALECT_EXIT_CODE=$?

if [ ${DIALECT_EXIT_CODE} -ne 0 ]; then
    echo "ERROR: Dialect test suite reported failures!"
    exit ${DIALECT_EXIT_CODE}
fi

echo ">> Shutting down dialect test containers..."
docker compose -f "${DIALECT_COMPOSE}" down -v --remove-orphans > /dev/null 2>&1 || true

# ------------------------------------------------------------------------------
# STEP 2: Real Production Stack Verification (app + db)
# ------------------------------------------------------------------------------
echo ""
echo ">> Step 4: Building and launching real production stack (app + db)..."

# Ensure temporary test .env exists if not present
if [ ! -f .env ]; then
    cp .env.example .env
fi

docker compose -f "${STACK_COMPOSE}" up -d --build --remove-orphans

echo ">> Step 5: Waiting for real stack /healthz endpoint..."
APP_HEALTHY=0
APP_WAIT=60
APP_COUNT=0

while [ ${APP_COUNT} -lt ${APP_WAIT} ]; do
    sleep 2
    APP_COUNT=$((APP_COUNT + 2))
    
    # Query /healthz directly inside the app container
    HEALTH_OUTPUT=$(docker compose -f "${STACK_COMPOSE}" exec -T app python -c \
        "import urllib.request, json; res = json.loads(urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read().decode()); print(f\"{res.get('status')}:{res.get('database')}\")" 2>/dev/null || true)

    if [ "${HEALTH_OUTPUT}" = "healthy:connected" ]; then
        APP_HEALTHY=1
        break
    fi
    echo "   Waiting for app & database connection (${APP_COUNT}s)... status: [${HEALTH_OUTPUT:-starting}]"
done

# ------------------------------------------------------------------------------
# STEP 3: Pass/Fail Summary Report
# ------------------------------------------------------------------------------
echo ""
echo "===================================================================="
if [ ${DIALECT_EXIT_CODE} -eq 0 ] && [ ${APP_HEALTHY} -eq 1 ]; then
    echo "   VERIFICATION SUCCESS: Full production verification PASSED!       "
    echo "   - PostgreSQL 16 Dialect (Migrations & CRUD): PASSED              "
    echo "   - MySQL 8.0 Dialect (Migrations & CRUD):     PASSED              "
    echo "   - MariaDB 11.2 Dialect (Migrations & CRUD):  PASSED              "
    echo "   - Real Stack (docker compose up app + db):   PASSED              "
    echo "   - /healthz Probe (status=healthy, db=conn):  PASSED              "
    echo "===================================================================="
    exit 0
else
    echo "   VERIFICATION FAILED:                                             "
    echo "   - Dialect Tests: $([ ${DIALECT_EXIT_CODE} -eq 0 ] && echo 'PASSED' || echo 'FAILED') "
    echo "   - Real Stack Healthz: $([ ${APP_HEALTHY} -eq 1 ] && echo 'PASSED' || echo 'FAILED') "
    echo "===================================================================="
    exit 1
fi
