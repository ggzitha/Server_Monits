#!/usr/bin/env python3
"""
seed_dev_admin.py - Local Development Admin Seeder
Creates or updates the dev 'admin' account with a randomly generated secure password.
Never hardcodes any credentials.
"""
import asyncio
import os
import secrets
import string
import sys
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Force development mode if not set
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///server_monits_dev.db")

from sqlalchemy import select
from backend.app.core.security import hash_password
from backend.app.db.base import Base
from backend.app.db.models.user import User, Role
from backend.app.db.models.system_config import SystemConfig
from backend.app.db.session import get_engine, get_session_factory


def generate_random_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    # Ensure at least one lower, upper, digit, and symbol
    pwd = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*"),
    ]
    pwd += [secrets.choice(alphabet) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(pwd)
    return "".join(pwd)


async def main():
    print("====================================================================")
    print("        Server_Monits: Local Development Admin Seeder               ")
    print("====================================================================")

    engine = get_engine()
    if engine is None:
        print("ERROR: Could not initialize database engine.")
        sys.exit(1)

    # 1. Create tables if needed
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = get_session_factory()
    async with session_factory() as session:
        # 2. Seed Default Roles if missing
        role_res = await session.execute(select(Role))
        existing_roles = {r.name: r for r in role_res.scalars().all()}

        if "Admin" not in existing_roles:
            admin_role = Role(
                name="Admin",
                description="System Administrator with full access",
                permissions=["*"],
                is_system=True,
            )
            session.add(admin_role)
            await session.flush()
            existing_roles["Admin"] = admin_role

        if "Viewer" not in existing_roles:
            viewer_role = Role(
                name="Viewer",
                description="Read-only observer",
                permissions=["plans:read", "sensors:read", "cctv:read"],
                is_system=True,
            )
            session.add(viewer_role)

        # 3. Generate Random Admin Password
        plain_password = generate_random_password(16)
        pw_hash = hash_password(plain_password)

        # 4. Check or Create Admin User
        user_res = await session.execute(select(User).where(User.username == "admin"))
        admin_user = user_res.scalar_one_or_none()

        if admin_user:
            admin_user.password_hash = pw_hash
            admin_user.is_active = True
            action_desc = "Updated existing"
        else:
            admin_user = User(
                username="admin",
                email="admin@dev.local",
                password_hash=pw_hash,
                is_active=True,
                preferred_lang="en",
                preferred_theme="neon",
            )
            admin_user.roles.append(existing_roles["Admin"])
            session.add(admin_user)
            action_desc = "Created new"

        # 5. Mark system as initialized
        cfg_res = await session.execute(select(SystemConfig).where(SystemConfig.key == "is_initialized"))
        cfg = cfg_res.scalar_one_or_none()
        if cfg:
            cfg.value = "true"
        else:
            session.add(SystemConfig(key="is_initialized", value="true"))

        await session.commit()

        print(f"\n>> {action_desc} admin account successfully:")
        print(f"   Username: admin")
        print(f"   Password: {plain_password}")
        print(f"   Role:     Admin (*)")
        print("\n>> Access URLs:")
        print("   Direct Backend: http://localhost:8000/login")
        print("   Vite Dev Server: http://localhost:5173 (with API proxy)")
        print("====================================================================")


if __name__ == "__main__":
    asyncio.run(main())

