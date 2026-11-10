from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from backend.app.api.deps import get_current_user, get_db, ensure_utc
from backend.app.core.audit import record_audit_log
from backend.app.core.config import settings
from backend.app.core.csrf import generate_csrf_token
from backend.app.core.security import (
    create_access_token,
    decrypt_secret,
    encrypt_secret,
    generate_backup_codes,
    generate_secure_token,
    generate_totp_secret,
    generate_totp_uri,
    hash_backup_code,
    hash_password,
    hash_token,
    verify_password,
    verify_totp_code,
)
from backend.app.db.models.auth_tokens import RefreshToken, TwoFactorSecret, UserSession, LoginAttempt
from backend.app.db.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = False


class TwoFactorVerifyRequest(BaseModel):
    temp_token: str
    totp_code: Optional[str] = None
    code: Optional[str] = None


class TwoFactorConfirmRequest(BaseModel):
    totp_code: str


class UpdateProfileRequest(BaseModel):
    current_password: Optional[str] = None
    new_password: Optional[str] = None
    preferred_lang: Optional[str] = None
    preferred_theme: Optional[str] = None


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.get("/csrf")
async def get_csrf_token(response: Response):
    """Obtain a fresh CSRF token and set the matching csrf_token cookie."""
    token = generate_csrf_token()
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=token,
        httponly=False,
        samesite="lax",
        secure=not settings.DEBUG,
    )
    return {"csrf_token": token}


@router.post("/login")
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user with DB-backed rate limiting and lockout tracking."""
    client_ip = get_client_ip(request)
    now = datetime.now(timezone.utc)
    lockout_cutoff = now - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)

    # Database-backed rate-limit & lockout check
    failed_attempts_stmt = select(func.count(LoginAttempt.id)).where(
        (LoginAttempt.ip_address == client_ip) | (LoginAttempt.username == req.username),
        LoginAttempt.success == False,
        LoginAttempt.attempted_at >= lockout_cutoff,
    )
    failed_count_res = await db.execute(failed_attempts_stmt)
    failed_attempts_count = failed_count_res.scalar_one()

    if failed_attempts_count >= settings.LOGIN_LOCKOUT_ATTEMPTS:
        db.add(LoginAttempt(ip_address=client_ip, username=req.username, success=False))
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account/IP is temporarily locked due to repeated failed logins. Please try again later.",
        )

    stmt = select(User).options(selectinload(User.roles)).where(User.username == req.username)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        db.add(LoginAttempt(ip_address=client_ip, username=req.username, success=False))
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Check user-specific lock timestamp
    if user.locked_until and ensure_utc(user.locked_until) > now:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is temporarily locked due to repeated failed logins. Please try again later.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    if not verify_password(req.password, user.password_hash):
        db.add(LoginAttempt(ip_address=client_ip, username=req.username, success=False))
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.LOGIN_LOCKOUT_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            await record_audit_log(
                db, "AUTH_LOCKOUT", user_id=user.id, details={"username": req.username}, request=request
            )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Login successful: record in DB
    db.add(LoginAttempt(ip_address=client_ip, username=req.username, success=True))
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    await db.commit()

    # Check if 2FA is required
    if user.is_totp_enabled:
        temp_token = create_access_token({"sub": user.id, "type": "2fa_pending"}, expires_delta=timedelta(minutes=5))
        return {
            "requires_2fa": True,
            "temp_token": temp_token,
            "message": "Enter your 2FA verification code or recovery backup code",
        }

    # Create Session & Tokens
    expire_hours = 24 * 7 if req.remember_me else settings.SESSION_EXPIRE_HOURS
    session_token = generate_secure_token(48)
    expires_at = now + timedelta(hours=expire_hours)

    user_session = UserSession(
        user_id=user.id,
        session_token=session_token,
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent", "")[:255],
        expires_at=expires_at,
    )
    db.add(user_session)

    # Refresh token
    raw_refresh = generate_secure_token(48)
    refresh_obj = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        expires_at=now + timedelta(days=30),
    )
    db.add(refresh_obj)
    await db.commit()

    # Issue JWT
    access_token = create_access_token({"sub": user.id, "username": user.username})

    # Set Session Cookie
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=not settings.DEBUG,
        max_age=expire_hours * 3600,
    )

    # Set CSRF Cookie
    csrf_token = generate_csrf_token()
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=not settings.DEBUG,
        max_age=expire_hours * 3600,
    )

    await record_audit_log(db, "AUTH_LOGIN", user_id=user.id, request=request)

    permissions = set()
    for role in user.roles:
        for p in role.permissions:
            permissions.add(p)

    return {
        "requires_2fa": False,
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "csrf_token": csrf_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "preferred_lang": user.preferred_lang,
            "preferred_theme": user.preferred_theme,
            "roles": [r.name for r in user.roles],
            "permissions": list(permissions),
        },
    }


@router.post("/2fa/verify")
async def verify_2fa(
    req: TwoFactorVerifyRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Complete 2FA login verification with 6-digit TOTP code OR single-use hashed recovery code."""
    from backend.app.core.security import decode_access_token
    payload = decode_access_token(req.temp_token)
    if not payload or payload.get("type") != "2fa_pending":
        raise HTTPException(status_code=400, detail="Invalid or expired 2FA session token")

    user_id = payload.get("sub")
    stmt = select(User).options(selectinload(User.roles)).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    # Fetch 2FA secret
    sec_stmt = select(TwoFactorSecret).where(TwoFactorSecret.user_id == user.id)
    sec_res = await db.execute(sec_stmt)
    two_fa_obj = sec_res.scalar_one_or_none()

    if not two_fa_obj:
        raise HTTPException(status_code=400, detail="2FA is not configured for this account")

    submitted_code = (req.code or req.totp_code or "").strip()
    if not submitted_code:
        raise HTTPException(status_code=400, detail="Verification code or backup code is required")

    is_verified = False
    used_backup = False

    # 1. Check if submitted code matches a single-use hashed recovery backup code
    candidate_hash = hash_backup_code(submitted_code)
    existing_hashes = list(two_fa_obj.recovery_codes_hash or [])
    if candidate_hash in existing_hashes:
        # Match! Remove the code so it is single-use only!
        existing_hashes.remove(candidate_hash)
        two_fa_obj.recovery_codes_hash = existing_hashes
        flag_modified(two_fa_obj, "recovery_codes_hash")
        is_verified = True
        used_backup = True
    else:
        # 2. Check 6-digit TOTP code
        secret = decrypt_secret(two_fa_obj.secret_encrypted)
        if verify_totp_code(secret, submitted_code):
            is_verified = True

    if not is_verified:
        raise HTTPException(status_code=400, detail="Invalid verification code or already used recovery code")

    now = datetime.now(timezone.utc)
    session_token = generate_secure_token(48)
    expires_at = now + timedelta(hours=settings.SESSION_EXPIRE_HOURS)

    user_session = UserSession(
        user_id=user.id,
        session_token=session_token,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:255],
        expires_at=expires_at,
    )
    db.add(user_session)
    await db.commit()

    access_token = create_access_token({"sub": user.id, "username": user.username})
    csrf_token = generate_csrf_token()

    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=not settings.DEBUG,
    )
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=not settings.DEBUG,
    )

    action = "AUTH_2FA_BACKUP_USED" if used_backup else "AUTH_2FA_SUCCESS"
    await record_audit_log(db, action, user_id=user.id, request=request)

    return {
        "success": True,
        "access_token": access_token,
        "csrf_token": csrf_token,
        "used_backup_code": used_backup,
        "remaining_backup_codes": len(two_fa_obj.recovery_codes_hash or []),
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "preferred_lang": user.preferred_lang,
            "preferred_theme": user.preferred_theme,
        },
    }


@router.post("/2fa/setup")
async def setup_2fa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initiate TOTP 2FA setup for current user and generate hashed single-use recovery codes."""
    secret = generate_totp_secret()
    uri = generate_totp_uri(secret, current_user.username)
    backup_codes = generate_backup_codes(8)
    backup_hashes = [hash_backup_code(c) for c in backup_codes]

    sec_stmt = select(TwoFactorSecret).where(TwoFactorSecret.user_id == current_user.id)
    sec_res = await db.execute(sec_stmt)
    two_fa_obj = sec_res.scalar_one_or_none()

    if not two_fa_obj:
        two_fa_obj = TwoFactorSecret(
            user_id=current_user.id,
            secret_encrypted=encrypt_secret(secret),
            recovery_codes_hash=backup_hashes,
            is_confirmed=False,
        )
        db.add(two_fa_obj)
    else:
        two_fa_obj.secret_encrypted = encrypt_secret(secret)
        two_fa_obj.recovery_codes_hash = backup_hashes
        flag_modified(two_fa_obj, "recovery_codes_hash")
        two_fa_obj.is_confirmed = False

    await db.commit()

    return {
        "secret": secret,
        "totp_uri": uri,
        "backup_codes": backup_codes,
        "message": "Scan the QR code or enter secret into your authenticator app, save your recovery backup codes safely, then confirm with a 6-digit code.",
    }


@router.post("/2fa/confirm")
async def confirm_2fa(
    req: TwoFactorConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm and activate 2FA using a verification code."""
    sec_stmt = select(TwoFactorSecret).where(TwoFactorSecret.user_id == current_user.id)
    sec_res = await db.execute(sec_stmt)
    two_fa_obj = sec_res.scalar_one_or_none()

    if not two_fa_obj:
        raise HTTPException(status_code=400, detail="2FA setup not initiated")

    secret = decrypt_secret(two_fa_obj.secret_encrypted)
    if not verify_totp_code(secret, req.totp_code):
        raise HTTPException(status_code=400, detail="Invalid verification code")

    two_fa_obj.is_confirmed = True
    current_user.is_totp_enabled = True
    await db.commit()

    return {"success": True, "message": "Two-factor authentication successfully enabled!"}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    session_token: Optional[str] = Cookie(None, alias=settings.SESSION_COOKIE_NAME),
):
    """Terminate session and revoke cookies."""
    if session_token:
        stmt = select(UserSession).where(UserSession.session_token == session_token)
        res = await db.execute(stmt)
        sess = res.scalar_one_or_none()
        if sess:
            await db.delete(sess)
            await db.commit()

    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    response.delete_cookie(settings.CSRF_COOKIE_NAME)
    await record_audit_log(db, "AUTH_LOGOUT", user_id=current_user.id, request=request)
    return {"success": True, "message": "Logged out successfully"}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Return authenticated user profile and permissions."""
    permissions = set()
    for role in current_user.roles:
        for p in role.permissions:
            permissions.add(p)

    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "preferred_lang": current_user.preferred_lang,
        "preferred_theme": current_user.preferred_theme,
        "is_totp_enabled": current_user.is_totp_enabled,
        "roles": [r.name for r in current_user.roles],
        "permissions": list(permissions),
    }


@router.put("/me")
async def update_profile(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user preferences or password."""
    if req.new_password:
        if not req.current_password or not verify_password(req.current_password, current_user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is required and must match")
        if len(req.new_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        current_user.password_hash = hash_password(req.new_password)

    if req.preferred_lang in ("en", "id"):
        current_user.preferred_lang = req.preferred_lang
    if req.preferred_theme in ("neon", "light"):
        current_user.preferred_theme = req.preferred_theme

    await db.commit()
    return {"success": True, "message": "Profile updated successfully"}
