from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENFINANCE_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = Field(
        default="postgresql+psycopg://openfinance:openfinance@localhost:5432/openfinance",
        validation_alias="DATABASE_URL",
    )
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "INFO"
    session_cookie_name: str = "of_session"
    session_cookie_secure: bool | None = None
    """Por defecto: activada en producción y desactivada en desarrollo."""
    session_ttl_days: int = Field(default=30, ge=1, le=365)
    login_max_failures_per_email: int = Field(default=5, ge=1)
    login_max_failures_per_ip: int = Field(default=20, ge=1)
    login_window_minutes: int = Field(default=15, ge=1)

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        if "*" in self.cors_origins:
            raise ValueError("OPENFINANCE_CORS_ORIGINS no admite '*' con cookies de sesión")
        return self

    @property
    def cookie_secure(self) -> bool:
        if self.session_cookie_secure is None:
            return self.environment == "production"
        return self.session_cookie_secure

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
