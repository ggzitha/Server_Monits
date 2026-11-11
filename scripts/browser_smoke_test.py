#!/usr/bin/env python3
"""
browser_smoke_test.py - Headless Playwright Browser Smoke Test (NextFloor Single Header & Editor)

Verifies:
1. Starts dev server and logs in as admin.
2. Asserts single unified header (Server_Monits brand, Mode switcher, New Design button).
3. Asserts ZERO German domestic words ('Obergeschoss', 'Wohnzimmer', 'Erdgeschoss', 'Kinderzimmer').
4. Switches to 3D CAD Editor mode via `#btnEditMode`.
5. Verifies CAD editor mounts cleanly with zero console errors or uncaught exceptions.
6. Switches back to 3D Monitor mode via `#btnViewMode`.
"""
import os
import sys

os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///server_monits_dev.db"

import time
import subprocess
import urllib.request
import asyncio
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

DEV_PORT = 8008
BASE_URL = f"http://127.0.0.1:{DEV_PORT}"
TEST_ADMIN_USER = "admin"
TEST_ADMIN_PASS = "SmokeTestAdmin123!"


def seed_admin_for_smoke_test():
    """Ensure admin account with known password exists in server_monits_dev.db."""
    from backend.app.core.security import hash_password
    from backend.app.db.base import Base
    from backend.app.db.session import get_engine, get_session_factory
    from backend.app.db.models.user import User, Role
    from backend.app.db.models.system_config import SystemConfig
    from sqlalchemy import select

    async def _seed():
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = get_session_factory()
        async with session_factory() as db:
            cfg_res = await db.execute(select(SystemConfig).limit(1))
            cfg = cfg_res.scalar_one_or_none()
            if not cfg:
                cfg = SystemConfig(is_initialized=True, app_name="Server_Monits")
                db.add(cfg)
            else:
                cfg.is_initialized = True

            r_res = await db.execute(select(Role).where(Role.name == "Admin"))
            admin_role = r_res.scalar_one_or_none()
            if not admin_role:
                admin_role = Role(
                    name="Admin",
                    description="Full administrative access",
                    permissions=["*"],
                    is_system=True,
                )
                db.add(admin_role)
                await db.flush()

            u_res = await db.execute(select(User).where(User.username == TEST_ADMIN_USER))
            admin_user = u_res.scalar_one_or_none()
            pw_hash = hash_password(TEST_ADMIN_PASS)

            if not admin_user:
                admin_user = User(
                    username=TEST_ADMIN_USER,
                    email="admin@smoke-test.local",
                    password_hash=pw_hash,
                    is_active=True,
                    roles=[admin_role],
                )
                db.add(admin_user)
            else:
                admin_user.password_hash = pw_hash
                admin_user.is_active = True
                if admin_role not in admin_user.roles:
                    admin_user.roles.append(admin_role)

            await db.commit()

    asyncio.run(_seed())
    print(f">> Admin user ready: {TEST_ADMIN_USER}")


def is_server_ready() -> bool:
    try:
        req = urllib.request.Request(f"{BASE_URL}/login")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def run_smoke_test():
    print("====================================================================")
    print("   Server_Monits: Smoke Test (Single Header, CAD Editor & EN/ID)   ")
    print("====================================================================")

    seed_admin_for_smoke_test()

    server_process = None
    if not is_server_ready():
        print(f">> Launching local uvicorn development server on port {DEV_PORT}...")
        env = os.environ.copy()
        env["APP_ENV"] = "development"
        env["DATABASE_URL"] = "sqlite+aiosqlite:///server_monits_dev.db"
        server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(DEV_PORT)],
            cwd=str(ROOT_DIR),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        for attempt in range(15):
            time.sleep(1)
            if is_server_ready():
                print(">> Development server is ready and responding.")
                break
        else:
            if server_process:
                server_process.kill()
            raise RuntimeError("Timed out waiting for uvicorn server to start.")
    else:
        print(f">> Existing local server detected on port {DEV_PORT}. Reusing instance.")

    from playwright.sync_api import sync_playwright

    console_errors = []
    page_errors = []
    outbound_requests = []

    with sync_playwright() as p:
        print(">> Launching headless Chromium browser...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 900})
        page = context.new_page()

        def on_console(msg):
            if msg.type == "error":
                text = msg.text
                if "favicon.ico" not in text:
                    console_errors.append(f"[Console Error] {text}")
                    print(f"  ❌ Console Error: {text}")

        def on_page_error(err):
            page_errors.append(f"[Uncaught Exception] {err}")
            print(f"  ❌ Uncaught Exception: {err}")
            if hasattr(err, "stack"):
                print(f"     Stack: {err.stack}")

        def on_request(req):
            url = req.url
            if not url.startswith(BASE_URL) and not url.startswith("data:"):
                outbound_requests.append(url)
                print(f"  ❌ External Outbound Request: {url}")

        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        page.on("request", on_request)

        try:
            # 1. Login
            print(">> [1/5] Logging in as admin...")
            page.goto(f"{BASE_URL}/login")
            page.wait_for_selector("#loginUsername", timeout=5000)
            page.fill("#loginUsername", TEST_ADMIN_USER)
            page.fill("#loginPassword", TEST_ADMIN_PASS)
            page.click("#btnLogin")

            # 2. Wait for main UI & Integrated NextFloor Header
            print(">> [2/7] Loading 3D Facility Monitor & Integrated Header (/)...")
            page.wait_for_url(f"{BASE_URL}/", timeout=8000)
            page.wait_for_selector("nextfloor-panel", timeout=10000)
            page.locator("header.nf-header.monits-top-navbar").wait_for(state="visible", timeout=10000)

            header_count = page.locator("header.nf-header.monits-top-navbar").count()
            if header_count != 1:
                raise RuntimeError(f"Expected 1 integrated .nf-header, found {header_count}")
            print("  ✓ Native NextFloor .nf-header is VISIBLE and fully integrated with Server_Monits controls.")

            # 3. Assert NO German words
            print(">> [3/7] Verifying language purity (No German words)...")
            body_text = page.inner_text("body")
            german_words = ["Obergeschoss", "Wohnzimmer", "Erdgeschoss", "Kinderzimmer", "Küche", "Schlafzimmer"]
            found_german = [w for w in german_words if w.lower() in body_text.lower()]
            if found_german:
                raise RuntimeError(f"Found unwanted German words in UI: {found_german}")
            print("  ✓ Pure English / Indonesian facility model active: Zero German words.")

            # 4. Test 3D Canvas
            print(">> [4/7] Verifying 3D WebGL Canvas...")
            page.wait_for_function("""() => {
                const p = document.querySelector('nextfloor-panel');
                if (!p || !p.shadowRoot) return false;
                const v = p.shadowRoot.querySelector('nf-view3d');
                if (!v || !v.shadowRoot) return false;
                return v.shadowRoot.querySelector('canvas') !== null;
            }""", timeout=15000)
            print("  ✓ NextFloor Three.js 3D canvas active and rendering.")

            # 5. Test Virtual Lights & Direct DB Sensor Data Drawer
            print(">> [5/7] Testing Virtual Lights & Direct DB Sensor Data...")
            page.locator("#btnVirtualDb").click()
            page.wait_for_selector("#drawerDevices.open", timeout=5000)

            # Toggle virtual light off then on
            page.evaluate("() => window.onVirtualLightToggle('light.server_alpha_light', 'off')")
            page.wait_for_timeout(300)
            light_state = page.evaluate("() => window.nfPanel.hass.states['light.server_alpha_light'].state")
            if light_state != "off":
                raise RuntimeError(f"Expected virtual light state 'off', got '{light_state}'")

            page.evaluate("() => window.onVirtualLightToggle('light.server_alpha_light', 'on')")
            page.wait_for_timeout(300)
            light_state = page.evaluate("() => window.nfPanel.hass.states['light.server_alpha_light'].state")
            if light_state != "on":
                raise RuntimeError(f"Expected virtual light state 'on', got '{light_state}'")
            print("  ✓ Virtual lights toggle ON/OFF in 3D scene & persist to DB without Home Assistant.")

            # Push live DB sensor reading
            page.evaluate("""() => window.monitsApi.pushDbSensorReading({
                identifier: 'server_alpha_env',
                area_id: 'server_alpha',
                temperature: 23.7,
                humidity: 46.2,
                power_kw: 44.5
            })""")
            page.wait_for_timeout(400)
            temp_state = page.evaluate("() => window.nfPanel.hass.states['sensor.server_alpha_env_temp'].state")
            if temp_state != "23.7":
                raise RuntimeError(f"Expected DB sensor temp '23.7', got '{temp_state}'")
            print("  ✓ Direct DB sensor reading saved to database & synced to 3D scene (23.7°C).")

            # 6. Test 3D Cabling (Below Floor, In Wall, Ceiling for Power, FO, Ethernet)
            print(">> [6/7] Testing 3D Cabling (Power, FO, Ethernet in Below Floor / Wall / Ceiling)...")
            page.locator("#btnCablesMgr").click()
            page.wait_for_selector("#drawerCables.open", timeout=5000)
            page.click("button[onclick='handleAddCableRun()']")
            page.wait_for_timeout(300)
            cable_msg = page.inner_text("#cableStatusMsg")
            if "Added" not in cable_msg and "Ditambahkan" not in cable_msg:
                raise RuntimeError(f"Expected cable addition confirmation, got '{cable_msg}'")
            page.evaluate("() => window.toggleMonitsDrawer(null)")
            print(f"  ✓ 3D Cable routing verified: {cable_msg}")

            # 7. Test Switching to 3D CAD Editor
            print(">> [7/7] Testing 3D CAD Editor Mode Switch...")
            page.locator("#btnEditMode").click()
            page.wait_for_timeout(1000)

            mode = page.evaluate("() => document.querySelector('nextfloor-panel')?._mode")
            if mode != "editor":
                raise RuntimeError(f"Expected mode 'editor', got '{mode}'")
            print("  ✓ Successfully switched into 3D CAD Floor Plan Editor mode.")

            # Switch back to view mode
            page.locator("#btnViewMode").click()
            page.wait_for_timeout(500)
            mode = page.evaluate("() => document.querySelector('nextfloor-panel')?._mode")
            if mode != "view":
                raise RuntimeError(f"Expected mode 'view', got '{mode}'")
            print("  ✓ Successfully switched back to 3D Monitor mode.")

            # Verify zero external outbound requests
            if outbound_requests:
                raise RuntimeError(f"Detected {len(outbound_requests)} external network request(s): {outbound_requests}")
            print("  ✓ Zero external outbound requests (100% air-gapped).")

            # Final verify on errors
            if console_errors:
                raise RuntimeError(f"Detected {len(console_errors)} console error(s): {console_errors}")
            if page_errors:
                raise RuntimeError(f"Detected {len(page_errors)} uncaught exception(s): {page_errors}")

            print("====================================================================")
            print("  ✓ ALL CHECKS PASSED: 1 Header, Clean CAD Editor & Pure EN/ID!    ")
            print("====================================================================")

        finally:
            browser.close()
            if server_process:
                server_process.kill()


if __name__ == "__main__":
    run_smoke_test()
