from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from openfinance.infrastructure.config import get_settings


def utc_now() -> datetime:
    return datetime.now(UTC)


def local_today() -> date:
    """Hoy en la zona horaria del hogar (los extractos usan hora local)."""
    return utc_now().astimezone(ZoneInfo(get_settings().timezone)).date()
