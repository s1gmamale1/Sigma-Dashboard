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
    sheet_sync_hour: int = 19
    sheet_sync_minute: int = 0
    frontend_dist_path: str = "frontend/dist"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SIGMA_",
        extra="ignore",
    )

    @property
    def frontend_dist(self) -> Path:
        return Path(self.frontend_dist_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
