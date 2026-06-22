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
    # Auto-sync imports the HR sheet on this fixed interval so History tracks the sheet
    # within minutes. The loop floors the effective cadence at 60s, so a 0/negative
    # value can never busy-loop the Sheets API — it is treated as a 1-minute interval.
    sheet_sync_interval_minutes: int = 10
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

    # --- HQ control plane (read-only MVP) ---
    # Paths to upstream state files (env only: SIGMA_HQ_SIGMACONTROL_STATE /
    # SIGMA_HQ_SIGMALINK_STATE). Unset/missing → that source reports unhealthy and
    # contributes nothing; the mock source then keeps the UI populated with clearly
    # labeled sample data until the real source path + schema are confirmed.
    hq_sigmacontrol_state: str | None = None
    hq_sigmalink_state: str | None = None
    # Live SigmaLink External Control socket. Prefer SIGMA_HQ_SIGMALINK_SOCKET /
    # SIGMA_HQ_SIGMALINK_TOKEN for the dashboard process; it also falls back to
    # SIGMA_CONTROL_SOCKET / SIGMA_CONTROL_TOKEN for local operator runs.
    hq_sigmalink_socket: str | None = None
    hq_sigmalink_token: str | None = None
    hq_sigmalink_label: str = "sigma-hq"
    hq_control_creds_path: str | None = None
    control_socket: str | None = None
    control_token: str | None = None
    # Include the mock source so the HQ tab is never empty pre-integration. Mock
    # rows are visibly labeled in the UI; set SIGMA_HQ_USE_MOCK=false once live
    # sources are wired and confirmed.
    hq_use_mock: bool = True
    hq_cache_ttl_seconds: int = 5
    hq_heartbeat_stale_seconds: int = 120
    # Control/write actions stay OFF by default — read-first, write-later. Even when
    # enabled they require an explicit X-Sigma-Signoff header and still return 501
    # (nothing is wired in the MVP).
    hq_allow_actions: bool = False

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
