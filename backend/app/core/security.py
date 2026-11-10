import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple, List
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet

from backend.app.core.config import settings

# Initialize Argon2id password hasher with secure defaults
ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against an Argon2id hash."""
    try:
        return ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, Exception):
        return False


def get_fernet_cipher() -> Fernet:
    """Get Fernet cipher initialized with the configured key."""
    key = settings.FERNET_KEY
    if not key:
        raise ValueError("FERNET_KEY is not configured")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plain_text: str) -> str:
    """Encrypt sensitive string (e.g. camera passwords, API credentials)."""
    if not plain_text:
        return ""
    cipher = get_fernet_cipher()
    return cipher.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted_text: str) -> str:
    """Decrypt sensitive string."""
    if not encrypted_text:
        return ""
    cipher = get_fernet_cipher()
    return cipher.decrypt(encrypted_text.encode("utf-8")).decode("utf-8")


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure URL-safe token."""
    return secrets.token_urlsafe(length)


def hash_token(token: str) -> str:
    """Hash an API token or session token with SHA-256 for secure DB storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except Exception:
        return None


# --- RFC 6238 TOTP 2FA & Backup Codes Implementation ---

def generate_totp_secret() -> str:
    """Generate a random base32 encoded secret for TOTP (160 bits)."""
    random_bytes = os.urandom(20)
    return base64.b32encode(random_bytes).decode("utf-8").replace("=", "")


def get_totp_code(secret: str, time_step: int = 30, for_time: Optional[int] = None) -> str:
    """Calculate current 6-digit TOTP code for a given base32 secret."""
    if for_time is None:
        for_time = int(time.time())
    
    counter = int(for_time // time_step)
    # Pad secret if missing padding
    missing_padding = len(secret) % 8
    if missing_padding != 0:
        secret += "=" * (8 - missing_padding)
    
    key = base64.b32decode(secret.upper())
    counter_bytes = struct.pack(">Q", counter)
    
    h = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = struct.unpack(">I", h[offset:offset+4])[0] & 0x7FFFFFFF
    return f"{code % 1000000:06d}"


def verify_totp_code(secret: str, code: str, window: int = 1) -> bool:
    """Verify a 6-digit TOTP code with time drift window tolerance."""
    if not code or len(code.strip()) != 6:
        return False
    
    code = code.strip()
    current_time = int(time.time())
    
    for offset in range(-window, window + 1):
        test_time = current_time + (offset * 30)
        try:
            expected = get_totp_code(secret, for_time=test_time)
            if hmac.compare_digest(expected, code):
                return True
        except Exception:
            continue
    return False


def generate_totp_uri(secret: str, username: str, issuer: str = "ServerMonits") -> str:
    """Generate otpauth:// URI for authenticator apps (Google Auth, Microsoft Auth, etc)."""
    return f"otpauth://totp/{issuer}:{username}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"


def generate_backup_codes(count: int = 8) -> List[str]:
    """Generate human-readable random 2FA recovery backup codes (e.g. ['a1b2-c3d4', ...])."""
    codes = []
    for _ in range(count):
        part1 = secrets.token_hex(2)
        part2 = secrets.token_hex(2)
        codes.append(f"{part1}-{part2}")
    return codes


def hash_backup_code(code: str) -> str:
    """Hash a backup recovery code for secure single-use storage."""
    clean_code = code.strip().lower().replace(" ", "").replace("-", "")
    salted = f"{settings.SECRET_KEY}:{clean_code}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()
