"""categories and rules

Revision ID: 0004_categories
Revises: 0003_imports
Create Date: 2026-10-31

Crea las categorías por hogar y las reglas por comercio, y migra los datos existentes:
- cada hogar recibe las 13 categorías de serie;
- ``transactions.category`` (texto) pasa a ``category_id``: si el texto coincide con el
  identificador de una categoría de serie se enlaza con ella; si no, se crea una categoría
  propia con ese nombre;
- se calcula ``transactions.merchant`` (comercio normalizado) a partir del concepto.
"""

import re
import unicodedata
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_categories"
down_revision: str | None = "0003_imports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Copia congelada de las categorías de serie en el momento de esta migración.
DEFAULTS = (
    ("vivienda", "Vivienda", "🏠", "#0f766e"),
    ("super", "Supermercado", "🛒", "#16a34a"),
    ("suministros", "Luz, agua, gas e internet", "💡", "#ca8a04"),
    ("restaurantes", "Restaurantes", "🍽️", "#ea580c"),
    ("transporte", "Transporte", "🚗", "#2563eb"),
    ("suscripciones", "Suscripciones", "📺", "#7c3aed"),
    ("salud", "Salud y deporte", "💪", "#db2777"),
    ("ocio", "Ocio", "🎟️", "#0891b2"),
    ("ropa", "Ropa", "👕", "#9333ea"),
    ("hogar", "Hogar", "🛋️", "#65a30d"),
    ("viajes", "Viajes", "✈️", "#0284c7"),
    ("regalos", "Regalos", "🎁", "#e11d48"),
    ("otros", "Otros", "📦", "#64748b"),
)

# Copia congelada del normalizador en el momento de esta migración, para que el resultado
# no cambie si más adelante cambia ``openfinance.domain.categories.merchant_key``.
_PREFIXES = re.compile(
    r"^(?:COMPRA(?: EN| CON TARJETA| TARJETA)?|PAGO(?: CON TARJETA| EN| A)?|"
    r"RECIBO(?: DE)?|ADEUDO(?: DE)?|CARGO(?: DE| EN)?|CARD PAYMENT(?: TO)?|PAYMENT (?:TO|FROM)|"
    r"TRANSFERENCIA (?:A|DE)|TRANSFER (?:FROM|TO)|BIZUM (?:A|DE)|CASH AT|TARJETA|TO)(?:\s+|$)"
)
_STOP = {
    "SL",
    "SA",
    "SLU",
    "SAU",
    "SARL",
    "SAS",
    "GMBH",
    "LTD",
    "INC",
    "BV",
    "COM",
    "ES",
    "EU",
    "WWW",
}
_GENERIC = {"PAGO", "COMPRA", "TARJETA", "RECIBO", "CARGO", "ADEUDO", "TRANSFERENCIA"}


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).upper().split())


def merchant_key(description: str) -> str:
    text = re.sub(r"[^A-Z0-9 ]+", " ", normalize_text(description))
    text = " ".join(w for w in text.split() if not re.search(r"\d", w))
    previous = None
    while previous != text:
        previous, text = text, _PREFIXES.sub("", text)
    words = [w for w in text.split() if len(w) > 1 and w not in _STOP]
    if all(w in _GENERIC for w in words):
        return ""
    return " ".join(words[:3])[:100]


categories = sa.table(
    "categories",
    sa.column("id", sa.Uuid()),
    sa.column("household_id", sa.Uuid()),
    sa.column("name", sa.String()),
    sa.column("key", sa.String()),
    sa.column("icon", sa.String()),
    sa.column("color", sa.String()),
    sa.column("hidden", sa.Boolean()),
    sa.column("slug", sa.String()),
    sa.column("position", sa.Integer()),
)
transactions = sa.table(
    "transactions",
    sa.column("id", sa.Uuid()),
    sa.column("household_id", sa.Uuid()),
    sa.column("description", sa.String()),
    sa.column("category", sa.String()),
    sa.column("category_id", sa.Uuid()),
    sa.column("merchant", sa.String()),
)
households = sa.table("households", sa.column("id", sa.Uuid()))


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("icon", sa.String(length=16), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("slug", sa.String(length=30), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["household_id"], ["households.id"], name=op.f("fk_categories_household_id_households")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("household_id", "key", name="uq_categories_household_key"),
        sa.UniqueConstraint("id", "household_id", name="uq_categories_id_household"),
    )
    op.create_index(
        op.f("ix_categories_household_id"), "categories", ["household_id"], unique=False
    )
    op.create_table(
        "category_rules",
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=36), nullable=False),
        sa.Column("merchant", sa.String(length=100), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id", "household_id"],
            ["categories.id", "categories.household_id"],
            name="fk_category_rules_category_household",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_category_rules_household_id_households"),
        ),
        sa.PrimaryKeyConstraint(
            "household_id", "scope", "merchant", name=op.f("pk_category_rules")
        ),
    )
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("category_id", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column("merchant", sa.String(length=100), nullable=False, server_default="")
        )

    _migrate_data()

    with op.batch_alter_table("transactions") as batch:
        batch.create_index(
            "ix_transactions_household_merchant", ["household_id", "merchant"], unique=False
        )
        batch.create_foreign_key(
            "fk_transactions_category_household",
            "categories",
            ["category_id", "household_id"],
            ["id", "household_id"],
        )
        batch.drop_column("category")


def _migrate_data() -> None:
    conn = op.get_bind()
    # Por hogar: clave normalizada (la misma que se guarda en ``key``) → id de categoría.
    by_household: dict[uuid.UUID, dict[str, uuid.UUID]] = {}
    for (household_id,) in conn.execute(sa.select(households.c.id)):
        known: dict[str, uuid.UUID] = {}
        for position, (slug, name, icon, color) in enumerate(DEFAULTS):
            cid = uuid.uuid4()
            key = normalize_text(name)[:50]
            conn.execute(
                categories.insert().values(
                    id=cid,
                    household_id=household_id,
                    name=name,
                    key=key,
                    icon=icon,
                    color=color,
                    hidden=False,
                    slug=slug,
                    position=position,
                )
            )
            known[f"slug:{slug}"] = cid
            known[key] = cid
        by_household[household_id] = known

    next_position = dict.fromkeys(by_household, len(DEFAULTS))
    updates = []
    rows = conn.execute(
        sa.select(
            transactions.c.id,
            transactions.c.household_id,
            transactions.c.description,
            transactions.c.category,
        )
    )
    for tx_id, household_id, description, old in rows:
        category_id = None
        name = (old or "").strip()[:50]
        if name:
            known = by_household[household_id]
            key = normalize_text(name)[:50]
            category_id = known.get(f"slug:{name}") or known.get(key)
            if category_id is None and key:
                category_id = uuid.uuid4()
                conn.execute(
                    categories.insert().values(
                        id=category_id,
                        household_id=household_id,
                        name=name,
                        key=key,
                        icon="🏷️",
                        color="#64748b",
                        hidden=False,
                        slug=None,
                        position=next_position[household_id],
                    )
                )
                next_position[household_id] += 1
                known[key] = category_id
        updates.append(
            {"tid": tx_id, "cid": category_id, "merchant": merchant_key(description or "")}
        )

    statement = (
        transactions.update()
        .where(transactions.c.id == sa.bindparam("tid"))
        .values(category_id=sa.bindparam("cid"), merchant=sa.bindparam("merchant"))
    )
    for i in range(0, len(updates), 1000):
        conn.execute(statement, updates[i : i + 1000])


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("category", sa.String(length=50), nullable=True))
    conn = op.get_bind()
    conn.execute(
        transactions.update().values(
            category=sa.select(sa.func.coalesce(categories.c.slug, categories.c.name))
            .where(categories.c.id == transactions.c.category_id)
            .scalar_subquery()
        )
    )
    with op.batch_alter_table("transactions") as batch:
        batch.drop_constraint("fk_transactions_category_household", type_="foreignkey")
        batch.drop_index("ix_transactions_household_merchant")
        batch.drop_column("merchant")
        batch.drop_column("category_id")
    op.drop_table("category_rules")
    op.drop_index(op.f("ix_categories_household_id"), table_name="categories")
    op.drop_table("categories")
