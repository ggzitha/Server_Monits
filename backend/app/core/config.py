import os
import re
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from cryptography.fernet import Fernet


# Determine project root directory (where .env lives)
CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent.parent
ROOT_DIR = BACKEND_DIR.parent
ENV_FILE = ROOT_DIR / ".env"
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT_DIR / "data"))
FERNET_KEY_FILE = DATA_DIR / "fernet.key"


def get_or_generate_fernet_key(existing_key: Optional[str] = None) -> str:
    """Return existing Fernet key from volume file or env, or generate and persist once."""
    if existing_key and len(existing_key.strip()) >= 32:
        # Also ensure volume file has this key
        _ensure_key_file(existing_key.strip())
        return existing_key.strip()
    
    # 1. Try reading from persistent volume file (/app/data/fernet.key)
    if FERNET_KEY_FILE.exists():
        try:
            key_from_file = FERNET_KEY_FILE.read_text(encoding="utf-8").strip()
            if len(key_from_file) >= 32:
                return key_from_file
        except Exception:
            pass

    # 2. Try reading directly from .env if present
    if ENV_FILE.exists():
        try:
            content = ENV_FILE.read_text(encoding="utf-8")
            match = re.search(r"^FERNET_KEY=(.+)$", content, re.MULTILINE)
            if match and len(match.group(1).strip()) >= 32:
                found_key = match.group(1).strip()
                _ensure_key_file(found_key)
                return found_key
        except Exception:
            pass

    # 3. Generate a brand-new Fernet key and persist to volume file and .env
    new_key = Fernet.generate_key().decode()
    _ensure_key_file(new_key)
    persist_env_variable("FERNET_KEY", new_key)
    return new_key


def _ensure_key_file(key: str) -> None:
    """Safely write key to persistent Docker volume path."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not FERNET_KEY_FILE.exists() or FERNET_KEY_FILE.read_text(encoding="utf-8").strip() != key:
            FERNET_KEY_FILE.write_text(key, encoding="utf-8")
    except Exception:
        pass


def persist_env_variable(key: str, value: str) -> None:
    """Safely append or update a variable in the external .env file."""
    try:
        if not ENV_FILE.exists():
            ENV_FILE.write_text(f"{key}={value}\n", encoding="utf-8")
            return

        content = ENV_FILE.read_text(encoding="utf-8")
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
        if pattern.search(content):
            new_content = pattern.sub(f"{key}={value}", content)
        else:
            if not content.endswith("\n"):
                content += "\n"
            new_content = content + f"{key}={value}\n"
        
        ENV_FILE.write_text(new_content, encoding="utf-8")
    except Exception as e:
        os.environ[key] = value


class Settings(BaseSettings):
    APP_NAME: str = "Server Room 3D Monitoring"
    APP_ENV: str = "production"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    
    # Security & Hashing
    SECRET_KEY: str = "default-insecure-secret-key-change-in-production-12345678"
    FERNET_KEY: str = ""
    
    # Database URL stored outside the DB
    DATABASE_URL: Optional[str] = None
    
    # Initial Admin Config (Required during Setup Wizard or via environment for auto-init)
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: Optional[str] = None
    ADMIN_EMAIL: str = "admin@datacenter.internal"
    
    # Preferences & Defaults
    DEFAULT_LANGUAGE: str = "en"  # "en" or "id"
    DEFAULT_THEME: str = "neon"   # "neon" or "light"
    
    # Cookie & Session configuration
    SESSION_COOKIE_NAME: str = "monit_session"
    SESSION_EXPIRE_HOURS: int = 24
    CSRF_COOKIE_NAME: str = "csrf_token"
    CSRF_HEADER_NAME: str = "x-csrf-token"
    
    # JWT & Rate Limiting
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    RATE_LIMIT_PER_MINUTE: int = 60
    LOGIN_LOCKOUT_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    
    # Stream Gateway (Existing Frigate go2rtc instance)
    GO2RTC_API_URL: str = "http://frigate:1984"
    
    # External MQTT Broker (Optional defaults for headless bootstrap)
    MQTT_HOST: Optional[str] = None
    MQTT_PORT: int = 1883
    MQTT_USERNAME: Optional[str] = None
    MQTT_PASSWORD: Optional[str] = None
    MQTT_TLS: bool = False
    MQTT_CLIENT_ID: str = "server_monits_client"
    
    # Retention
    TELEMETRY_RETENTION_DAYS: int = 90

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Instantiate settings
settings = Settings()

# Ensure Fernet key is generated and persisted once
if not settings.FERNET_KEY:
    settings.FERNET_KEY = get_or_generate_fernet_key(settings.FERNET_KEY)
