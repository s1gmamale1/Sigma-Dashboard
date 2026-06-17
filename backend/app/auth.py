import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .models import User
from .permissions import can_write

bearer_scheme = HTTPBearer(auto_error=False, description="User JWT from POST /api/v1/auth/login")
viper_scheme = APIKeyHeader(
    name="X-Viper-Token",
    auto_error=False,
    description="Shared secret for the Viper ingest agent (SIGMA_VIPER_TOKEN).",
)
MAX_BCRYPT_PASSWORD_BYTES = 72

# Distinct marker so the frontend can tell "you must rotate your temp password" apart
# from an ordinary 403. Carried in the error detail since the envelope code is generic.
PASSWORD_CHANGE_REQUIRED = "PASSWORD_CHANGE_REQUIRED"


def hash_password(password: str) -> str:
    """bcrypt-hash a password (12 rounds). Raises ValueError if it exceeds bcrypt's 72-byte limit."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError("Password is too long for bcrypt; use 72 UTF-8 bytes or fewer.")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def check_password(password: str, password_hash: str) -> bool:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(settings: Settings, subject: str, role: str) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    token = jwt.encode(
        {"sub": subject, "role": role, "exp": expires_at},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_at


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the bearer JWT.

    Loads the account from the DB on every request, so role changes and disables
    take effect immediately. Does NOT enforce the temp-password gate — that lets
    `/auth/me` and `/auth/change-password` work while a password change is pending.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    username = payload.get("sub")
    user = db.scalar(select(User).where(User.username == username)) if username else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return user


def _gate_password(user: User) -> None:
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{PASSWORD_CHANGE_REQUIRED}: set a new password before continuing",
        )


def require_view(user: User = Depends(get_current_user)) -> User:
    """Any active user past the temp-password gate (read access to data areas)."""
    _gate_password(user)
    return user


def require_edit(user: User = Depends(get_current_user)) -> User:
    """Active, gated, and allowed to write (admin/manager — not a read-only viewer)."""
    _gate_password(user)
    if not can_write(user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is read-only")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Active, gated, and an admin — for user management and other admin-only surfaces."""
    _gate_password(user)
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_viper(
    x_viper_token: str | None = Depends(viper_scheme),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> str:
    token = x_viper_token or (credentials.credentials if credentials else None)
    if not token or not secrets.compare_digest(
        token.encode("utf-8"), settings.viper_token.encode("utf-8")
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Viper token")
    return "viper"
