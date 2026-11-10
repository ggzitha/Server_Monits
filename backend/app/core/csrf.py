import secrets
from fastapi import Request, HTTPException, status
from backend.app.core.config import settings


def generate_csrf_token() -> str:
    """Generate a secure cryptographically random CSRF token."""
    return secrets.token_hex(32)


def validate_csrf_token(request: Request) -> None:
    """Validate CSRF token on mutating requests using double-submit cookie pattern.
    
    Skips validation for:
    - Safe HTTP methods (GET, HEAD, OPTIONS)
    - Bearer token authenticated API clients (e.g. Wi-Fi Survey Agent)
    - Specific public bootstrap routes (login, setup test)
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    # Check for Authorization header (Bearer token API clients bypass CSRF)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return

    # Whitelist specific endpoints that do not have an established session yet
    path = request.url.path
    if (
        path.endswith("/auth/login") or 
        path.endswith("/auth/2fa/verify") or 
        path.startswith("/api/v1/setup/") or
        path.startswith("/api/v1/webhook/")
    ):
        return

    # Check session cookie exists: if no session cookie, CSRF is not relevant
    session_cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_cookie:
        return

    # Double submit check: compare cookie value to header value
    cookie_token = request.cookies.get(settings.CSRF_COOKIE_NAME)
    header_token = request.headers.get(settings.CSRF_HEADER_NAME)

    if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF verification failed: Missing or invalid CSRF token"
        )

