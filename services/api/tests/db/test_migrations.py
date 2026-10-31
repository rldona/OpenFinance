import uuid

import sqlalchemy as sa
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


def test_0004_migrates_text_categories_and_merchants(tmp_path, monkeypatch) -> None:
    url = f"sqlite:///{tmp_path / 'data.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "0003_imports")
        engine = sa.create_engine(url)
        h, u, a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        ids = [uuid.uuid4() for _ in range(5)]
        with engine.begin() as c:
            c.execute(
                sa.text("INSERT INTO households (id, name, currency) VALUES (:h, 'Casa', 'EUR')"),
                {"h": h.hex},
            )
            c.execute(
                sa.text(
                    "INSERT INTO users (id, email, display_name, password_hash) VALUES (:u, 'r@e.org', 'R', 'x')"
                ),
                {"u": u.hex},
            )
            c.execute(
                sa.text("INSERT INTO memberships (household_id, user_id) VALUES (:h, :u)"),
                {"h": h.hex, "u": u.hex},
            )
            c.execute(
                sa.text(
                    "INSERT INTO accounts (id, household_id, name, institution, kind, currency, opening_balance) VALUES (:a, :h, 'C', 'revolut', 'joint', 'EUR', 0)"
                ),
                {"a": a.hex, "h": h.hex},
            )
            for tid, desc, cat in zip(
                ids,
                [
                    "MERCADONA 1234",
                    "VETERINARIO SAN ROQUE",
                    "GLOVO",
                    "PIENSO PERRO",
                    "PAGO CON TARJETA LIDL",
                ],
                ["super", "Mascotas", None, "  MASCOTAS ", "   "],
                strict=True,
            ):
                c.execute(
                    sa.text(
                        "INSERT INTO transactions (id, household_id, account_id, booked_at, value_date, description, amount, currency, kind, category, bank_type, source) "
                        "VALUES (:id, :h, :a, '2026-10-01 10:00:00', '2026-10-01', :d, -10, 'EUR', 'expense', :c, '', 'manual')"
                    ),
                    {"id": tid.hex, "h": h.hex, "a": a.hex, "d": desc, "c": cat},
                )

        command.upgrade(cfg, "head")
        with engine.connect() as c:
            cats = {r.name: r for r in c.execute(sa.text("SELECT * FROM categories"))}
            assert len(cats) == 14
            assert cats["Mascotas"].slug is None
            rows = {
                r.description: r
                for r in c.execute(
                    sa.text(
                        "SELECT t.description, t.merchant, c.name AS cat FROM transactions t "
                        "LEFT JOIN categories c ON c.id = t.category_id"
                    )
                )
            }
        assert rows["MERCADONA 1234"].cat == "Supermercado"
        assert rows["MERCADONA 1234"].merchant == "MERCADONA"
        assert rows["VETERINARIO SAN ROQUE"].cat == "Mascotas"
        assert rows["GLOVO"].cat is None
        assert rows["PIENSO PERRO"].cat == "Mascotas"  # misma clave normalizada
        assert rows["PAGO CON TARJETA LIDL"].cat is None  # solo espacios = sin categoría
        assert rows["PAGO CON TARJETA LIDL"].merchant == "LIDL"

        command.downgrade(cfg, "0003_imports")
        with engine.connect() as c:
            back = dict(c.execute(sa.text("SELECT description, category FROM transactions")).all())
        assert back == {
            "MERCADONA 1234": "super",
            "VETERINARIO SAN ROQUE": "Mascotas",
            "GLOVO": None,
            "PIENSO PERRO": "Mascotas",
            "PAGO CON TARJETA LIDL": None,
        }
        engine.dispose()
    finally:
        get_settings.cache_clear()
