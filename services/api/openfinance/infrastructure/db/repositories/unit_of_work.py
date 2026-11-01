"""Unidad de trabajo SQL: reúne los repositorios sobre una misma sesión."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from openfinance.application.errors import ConflictError
from openfinance.infrastructure.db.repositories.categories import (
    SqlCategoryRepository,
    SqlRuleRepository,
)
from openfinance.infrastructure.db.repositories.changes import SqlChangeRepository
from openfinance.infrastructure.db.repositories.identity import (
    SqlHouseholdRepository,
    SqlSessionRepository,
    SqlUserRepository,
)
from openfinance.infrastructure.db.repositories.imports import (
    SqlImportBatchRepository,
    SqlMemberPatternRepository,
)
from openfinance.infrastructure.db.repositories.ledger import (
    SqlAccountRepository,
    SqlTransactionRepository,
)
from openfinance.infrastructure.db.repositories.savings import (
    SqlBudgetRepository,
    SqlGoalRepository,
    SqlIdeaDismissalRepository,
)


class SqlUnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = SqlUserRepository(session)
        self.households = SqlHouseholdRepository(session)
        self.accounts = SqlAccountRepository(session)
        self.transactions = SqlTransactionRepository(session)
        self.sessions = SqlSessionRepository(session)
        self.imports = SqlImportBatchRepository(session)
        self.categories = SqlCategoryRepository(session)
        self.rules = SqlRuleRepository(session)
        self.budgets = SqlBudgetRepository(session)
        self.goals = SqlGoalRepository(session)
        self.dismissed_ideas = SqlIdeaDismissalRepository(session)
        self.member_patterns = SqlMemberPatternRepository(session)
        self.changes = SqlChangeRepository(session)

    def commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                "Los datos han cambiado mientras guardabas; vuelve a intentarlo"
            ) from exc
