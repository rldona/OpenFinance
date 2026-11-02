"""Repositorios SQL (implementan los puertos de `application.ports`), uno por contexto."""

from openfinance.infrastructure.db.repositories.attachments import SqlAttachmentRepository
from openfinance.infrastructure.db.repositories.automation import SqlAutomationRepository
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
from openfinance.infrastructure.db.repositories.links import SqlLinkRepository
from openfinance.infrastructure.db.repositories.merchants import SqlMerchantRepository
from openfinance.infrastructure.db.repositories.rates import SqlRateRepository
from openfinance.infrastructure.db.repositories.reconciliations import (
    SqlReconciliationRepository,
)
from openfinance.infrastructure.db.repositories.savings import (
    SqlBudgetRepository,
    SqlGoalRepository,
    SqlIdeaDismissalRepository,
)
from openfinance.infrastructure.db.repositories.splits import SqlSplitRepository
from openfinance.infrastructure.db.repositories.tags import SqlTagRepository
from openfinance.infrastructure.db.repositories.unit_of_work import SqlUnitOfWork

__all__ = [
    "SqlAccountRepository",
    "SqlAttachmentRepository",
    "SqlAutomationRepository",
    "SqlBudgetRepository",
    "SqlCategoryRepository",
    "SqlChangeRepository",
    "SqlGoalRepository",
    "SqlHouseholdRepository",
    "SqlIdeaDismissalRepository",
    "SqlImportBatchRepository",
    "SqlLinkRepository",
    "SqlMemberPatternRepository",
    "SqlMerchantRepository",
    "SqlRateRepository",
    "SqlReconciliationRepository",
    "SqlRuleRepository",
    "SqlSessionRepository",
    "SqlSplitRepository",
    "SqlTagRepository",
    "SqlTransactionRepository",
    "SqlUnitOfWork",
    "SqlUserRepository",
]
