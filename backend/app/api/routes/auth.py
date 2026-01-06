"""
Authentication routes with secure session management.

Uses JWT tokens stored in httpOnly cookies with CSRF protection.
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Response, Request, Cookie
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from jose import jwt, JWTError

from app.core.config import settings

router = APIRouter()
security = HTTPBasic(auto_error=False)

# Cookie settings
COOKIE_NAME = "session_token"
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
COOKIE_MAX_AGE = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # seconds

# JWT settings
JWT_ALGORITHM = "HS256"


class UserInfo(BaseModel):
    username: str
    role: str = "admin"


class LoginRequest(BaseModel):
    username: str
    password: str


def _create_access_token(username: str) -> str:
    """Create JWT access token"""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        # Use numeric timestamps for compatibility across JWT libs
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def _verify_token(token: str) -> Optional[str]:
    """Verify JWT token and return username if valid"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def _generate_csrf_token() -> str:
    """Generate a random CSRF token"""
    return secrets.token_urlsafe(32)


def _verify_credentials_internal(username: str, password: str) -> bool:
    """Verify admin credentials using constant-time comparison"""
    correct_username = secrets.compare_digest(
        username.encode("utf-8"),
        settings.ADMIN_USERNAME.encode("utf-8")
    )
    correct_password = secrets.compare_digest(
        password.encode("utf-8"),
        settings.ADMIN_PASSWORD.encode("utf-8")
    )
    return correct_username and correct_password


def _get_cookie_settings() -> dict:
    """Get cookie settings based on environment"""
    is_prod = settings.ENV == "prod"
    return {
        "httponly": True,
        "secure": is_prod,  # HTTPS only in production
        "samesite": "lax",  # Protects against CSRF for most cases
        "max_age": COOKIE_MAX_AGE,
    }


async def verify_session(
    request: Request,
    session_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
) -> str:
    """
    Verify user session via cookie JWT or Basic Auth header.
    
    Priority:
    1. Cookie-based JWT session (preferred, secure)
    2. Basic Auth header (fallback for API clients/backwards compatibility)
    
    Also verifies CSRF token for state-changing requests (POST/PUT/PATCH/DELETE).
    """
    username = None
    
    # Try cookie-based session first
    if session_token:
        username = _verify_token(session_token)
    
    # Fallback to Basic Auth for API clients
    if not username and credentials:
        if _verify_credentials_internal(credentials.username, credentials.password):
            username = credentials.username
    
    if not username:
        # Avoid triggering browser Basic-Auth prompts for cookie-based UI flows.
        # Only advertise Basic auth challenge when the client actually attempted it.
        headers = {"WWW-Authenticate": "Basic"} if credentials else None
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session",
            headers=headers,
        )
    
    # CSRF check for state-changing methods (when using cookies)
    if session_token and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
        csrf_header = request.headers.get(CSRF_HEADER_NAME)
        
        # Skip CSRF for file downloads and specific safe endpoints
        if not request.url.path.endswith(("/login", "/logout", "/me")):
            if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
                raise HTTPException(
                    status_code=403,
                    detail="CSRF token missing or invalid"
                )
    
    return username


# Legacy dependency for backwards compatibility
def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """Legacy: Verify admin credentials using Basic Auth only"""
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Credentials required",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    if not _verify_credentials_internal(credentials.username, credentials.password):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# Dependency to protect routes - supports both cookie and Basic Auth
require_admin = Depends(verify_session)


@router.post("/login")
async def login(request: LoginRequest, response: Response):
    """
    Login endpoint - validates credentials and sets session cookies.
    
    Sets:
    - session_token: httpOnly JWT cookie (not accessible to JS)
    - csrf_token: Regular cookie (readable by JS for CSRF protection)
    """
    if not _verify_credentials_internal(request.username, request.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Create JWT token
    access_token = _create_access_token(request.username)
    
    # Generate CSRF token
    csrf_token = _generate_csrf_token()
    
    cookie_settings = _get_cookie_settings()
    
    # Set httpOnly session cookie (secure, not accessible to JS)
    response.set_cookie(
        key=COOKIE_NAME,
        value=access_token,
        **cookie_settings
    )
    
    # Set CSRF cookie (readable by JS to include in headers)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,  # JS needs to read this
        secure=cookie_settings["secure"],
        samesite=cookie_settings["samesite"],
        max_age=cookie_settings["max_age"],
    )
    
    return {
        "message": "Login successful",
        "username": request.username,
        "csrf_token": csrf_token,  # Also return in body for initial setup
    }


@router.post("/logout")
async def logout(response: Response):
    """Logout - clear session cookies"""
    response.delete_cookie(COOKIE_NAME)
    response.delete_cookie(CSRF_COOKIE_NAME)
    return {"message": "Logged out"}


@router.get("/me", response_model=UserInfo)
async def get_current_user(username: str = Depends(verify_session)):
    """Get current user info (also serves as session verification)"""
    return UserInfo(username=username, role="admin")


@router.get("/csrf-token")
async def get_csrf_token(
    request: Request,
    response: Response,
    _: str = Depends(verify_session),
):
    """
    Get a new CSRF token. Call this if you need to refresh the token.
    Requires valid session.
    """
    csrf_token = _generate_csrf_token()
    
    cookie_settings = _get_cookie_settings()
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=cookie_settings["secure"],
        samesite=cookie_settings["samesite"],
        max_age=cookie_settings["max_age"],
    )
    
    return {"csrf_token": csrf_token}
