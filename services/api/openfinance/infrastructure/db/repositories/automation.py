"""Repositorio de reglas con condiciones (OF-1101)."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from openfinance.domain.automation import (
    AutomationRule,
    Phase,
    parse_actions,
    parse_conditions,
)
from openfinance.domain.shared.ids import UserId, WorkspaceId
from openfinance.infrastructure.db.models import AutomationRuleRow
from openfinance.infrastructure.db.repositories._common import _flush


def _rule(r: AutomationRuleRow) -> AutomationRule:
    return AutomationRule(
        id=r.id,
        household_id=WorkspaceId(r.household_id),
        scope=r.scope,
        name=r.name,
        phase=Phase(r.phase),
        priority=r.priority,
        enabled=r.enabled,
        conditions=parse_conditions(json.loads(r.conditions)),
        actions=parse_actions(json.loads(r.actions)),
    )


def _dump(items: object) -> str:
    return json.dumps(items, ensure_ascii=False, sort_keys=True)


class SqlAutomationRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def for_household(self, household_id: WorkspaceId) -> list[AutomationRule]:
        rows = self._s.scalars(
            select(AutomationRuleRow)
            .where(AutomationRuleRow.household_id == household_id)
            .order_by(AutomationRuleRow.phase, AutomationRuleRow.priority, AutomationRuleRow.id)
        )
        return [_rule(r) for r in rows]

    def get(self, household_id: WorkspaceId, rule_id: UUID) -> AutomationRule | None:
        row = self._s.scalar(
            select(AutomationRuleRow).where(
                AutomationRuleRow.id == rule_id, AutomationRuleRow.household_id == household_id
            )
        )
        return _rule(row) if row else None

    def save(self, rule: AutomationRule, created_by: UserId) -> None:
        """Crea la regla o la sustituye entera."""
        row = self._s.get(AutomationRuleRow, rule.id)
        if row is None:
            row = AutomationRuleRow(
                id=rule.id, household_id=rule.household_id, created_by=created_by
            )
            self._s.add(row)
        row.scope = rule.scope
        row.name = rule.name
        row.phase = rule.phase.value
        row.priority = rule.priority
        row.enabled = rule.enabled
        row.conditions = _dump([c.as_json() for c in rule.conditions])
        row.actions = _dump([a.as_json() for a in rule.actions])
        _flush(self._s)

    def delete(self, household_id: WorkspaceId, rule_id: UUID) -> None:
        self._s.execute(
            delete(AutomationRuleRow).where(
                AutomationRuleRow.id == rule_id, AutomationRuleRow.household_id == household_id
            )
        )
        _flush(self._s)
