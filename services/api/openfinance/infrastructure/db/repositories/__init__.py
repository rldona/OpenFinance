"""Repositorios SQL (implementan los puertos de `application.ports`), uno por contexto."""

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
from openfinance.infrastructure.db.repositories.merchants import SqlMerchantRepository
from openfinance.infrastructure.db.repositories.savings import (
    SqlBudgetRepository,
    SqlGoalRepository,
    SqlIdeaDismissalRepository,
)
from openfinance.infrastructure.db.repositories.tags import SqlTagRepository
from openfinance.infrastructure.db.repositories.unit_of_work import SqlUnitOfWork

__all__ = [
    "SqlAccountRepository",
    "SqlBudgetRepository",
    "SqlCategoryRepository",
    "SqlChangeRepository",
    "SqlGoalRepository",
    "SqlHouseholdRepository",
    "SqlIdeaDismissalRepository",
    "SqlImportBatchRepository",
    "SqlMemberPatternRepository",
    "SqlMerchantRepository",
    "SqlRuleRepository",
    "SqlSessionRepository",
    "SqlTagRepository",
    "SqlTransactionRepository",
    "SqlUnitOfWork",
    "SqlUserRepository",
]
