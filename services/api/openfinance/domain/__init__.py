"""Modelo de dominio financiero. Sin dependencias de frameworks (ADR-001, ADR-004)."""

BOUNDED_CONTEXTS: tuple[str, ...] = (
    "identity",
    "workspaces",
    "ledger",
    "categorization",
    "budgeting",
    "imports",
    "insights",
)
