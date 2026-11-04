import logging
from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LEVELS = (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENFINANCE_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = Field(
        default="postgresql+psycopg://openfinance:openfinance@localhost:5432/openfinance",
        validation_alias="DATABASE_URL",
    )
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "INFO"
    timezone: str = "Europe/Madrid"
    """Zona horaria del hogar: decide qué es «hoy» y el mes en curso."""
    session_cookie_name: str = "of_session"
    session_cookie_secure: bool | None = None
    """Por defecto: activada en producción y desactivada en desarrollo."""
    session_ttl_days: int = Field(default=30, ge=1, le=365)
    login_max_failures_per_email: int = Field(default=5, ge=1)
    login_max_failures_per_ip: int = Field(default=20, ge=1)
    login_window_minutes: int = Field(default=15, ge=1)
    attachments_dir: str = "data/attachments"
    """Carpeta de los adjuntos (OF-1007). En Docker es un volumen y entra en la copia."""
    update_check: bool = False
    """Avisar de versiones nuevas consultando GitHub (OF-907). Apagado por defecto."""
    update_repo: str = "rldona/OpenFinance"
    vapid_public_key: str = ""
    """Claves VAPID (Web Push, OF-1302). Sin las tres, las notificaciones están apagadas."""
    vapid_private_key: str = ""
    vapid_subject: str = ""
    """Contacto de quien envía, ``mailto:`` o https (lo exige el estándar)."""
    bank_app_id: str = ""
    """Aplicación en Enable Banking (ADR-0024). Sin las tres, la conexión está apagada."""
    bank_private_key: str = ""
    """El PEM de la clave privada de la aplicación. Se admite con ``\\n`` en una sola línea."""
    bank_redirect_url: str = ""
    """Adonde vuelve el banco tras autorizar: la raíz de la web, registrada en el agregador."""

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        if logging.getLevelName(self.log_level.upper()) not in _LEVELS:
            raise ValueError(f"OPENFINANCE_LOG_LEVEL no válido: {self.log_level}")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Zona horaria no válida: {self.timezone}") from exc
        if "*" in self.cors_origins:
            raise ValueError("OPENFINANCE_CORS_ORIGINS no admite '*' con cookies de sesión")
        return self

    @property
    def push_enabled(self) -> bool:
        return bool(self.vapid_public_key and self.vapid_private_key and self.vapid_subject)

    @property
    def bank_enabled(self) -> bool:
        return bool(self.bank_app_id and self.bank_private_key and self.bank_redirect_url)

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
