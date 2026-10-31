from alembic import command
from alembic.config import Config

from openfinance.infrastructure.config import get_settings


def test_migrations_apply_and_match_models(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'mig.db'}")
    get_settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        command.check(cfg)
        command.downgrade(cfg, "base")
    finally:
        get_settings.cache_clear()
