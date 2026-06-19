from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sigma Dashboard"
    timezone: str = "Asia/Tashkent"
    database_url: str = "sqlite:///./dashboard.db"
    jwt_secret: str = Field(default="change-me-in-env", min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480
    admin_username: str = "admin"
    admin_password: str | None = None
    admin_password_hash: str | None = None
    viper_token: str = Field(default="change-me-viper-token", min_length=16)
    google_credentials_path: str | None = None
    google_sheet_id: str | None = None
    google_sheet_name: str = "HR Department"
    attendance_tab: str = "Sigma Attendnace"
    sheet_sync_enabled: bool = True
    # The attendance import runs on this fixed interval so the History view tracks the
    # HR sheet within minutes. (sheet_sync_hour/minute are retained for compatibility
    # with existing .env files but are no longer used by the auto-sync loop.)
    sheet_sync_interval_minutes: int = 10
    sheet_sync_hour: int = 19
    sheet_sync_minute: int = 0
    frontend_dist_path: str = "frontend/dist"
    gateway_ws_url: str = "ws://127.0.0.1:18789"
    gateway_token: str = ""
    # Default to the read-only "viper-chat" agent (OpenClaw allows it only
    # Read/Grep/Glob — it cannot send_message / write sheets / edit cron), so a
    # missing or blank SIGMA_GATEWAY_AGENT can never fall back to the
    # action-capable live "viper". Set SIGMA_GATEWAY_AGENT=viper in .env for live-fire.
    gateway_agent: str = "viper-chat"
    gateway_session: str = "dashboard"
    assistant_enabled: bool = False
    assistant_idle_timeout_s: float = 120.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SIGMA_",
        extra="ignore",
    )

    @property
    def frontend_dist(self) -> Path:
        return Path(self.frontend_dist_path)

    @property
    def gateway_session_key(self) -> str:
        return f"agent:{self.gateway_agent}:{self.gateway_session}"

    def validate_runtime_secrets(self) -> None:
        """Extended secret guard for Settings instance (called in tests and at boot)."""
        if self.assistant_enabled and len(self.gateway_token) < 16:
            raise ValueError(
                "SIGMA_GATEWAY_TOKEN must be set (>=16 chars) when SIGMA_ASSISTANT_ENABLED is true"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


PLACEHOLDER_PREFIX = "change-me"


def validate_runtime_secrets(settings: Settings) -> None:
    """Refuse to boot with the shipped placeholder secrets — a missing .env would
    otherwise run with predictable JWT/Viper secrets that pass min_length."""
    bad = [
        name
        for name, value in (
            ("SIGMA_JWT_SECRET", settings.jwt_secret),
            ("SIGMA_VIPER_TOKEN", settings.viper_token),
        )
        if value.startswith(PLACEHOLDER_PREFIX)
    ]
    if bad:
        raise RuntimeError(f"placeholder secrets in use — set {', '.join(bad)} in .env")
    settings.validate_runtime_secrets()
