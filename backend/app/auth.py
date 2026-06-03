from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
import bcrypt
from jose import JWTError, jwt

from .config import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False, description="Admin JWT from POST /api/v1/auth/login")
viper_scheme = APIKeyHeader(
    name="X-Viper-Token",
    auto_error=False,
    description="Shared secret for the Viper ingest agent (SIGMA_VIPER_TOKEN).",
)
MAX_BCRYPT_PASSWORD_BYTES = 72


def verify_password(settings: Settings, password: str) -> bool:
    if settings.admin_password_hash:
        password_bytes = password.encode("utf-8")
        if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
            return False
        return bcrypt.checkpw(password_bytes, settings.admin_password_hash.encode("utf-8"))
    return bool(settings.admin_password and password == settings.admin_password)


def create_access_token(settings: Settings, subject: str) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    token = jwt.encode(
        {"sub": subject, "exp": expires_at},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_at


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> str:
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
    subject = payload.get("sub")
    if subject != settings.admin_username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return subject


def require_viper(
    x_viper_token: str | None = Depends(viper_scheme),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> str:
    token = x_viper_token or (credentials.credentials if credentials else None)
    if not token or token != settings.viper_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Viper token")
    return "viper"
