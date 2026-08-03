"""
Import every ORM model here so `Base.metadata` is fully populated for
Alembic autogenerate. Import this module (not the individual model modules)
from alembic/env.py.
"""
from app.modules.accounts.models import Account  # noqa: F401
from app.modules.accounts.cash_operations import AccountCashOperation  # noqa: F401
from app.modules.audit_logs.models import AuditLog  # noqa: F401
from app.modules.auth.models import RefreshToken  # noqa: F401
from app.modules.beneficiaries.models import Beneficiary  # noqa: F401
from app.modules.cards.models import Card  # noqa: F401
from app.modules.customers.models import Customer  # noqa: F401
from app.modules.exchange_rates.models import ExchangeRate  # noqa: F401
from app.modules.ledger_entries.models import LedgerEntry  # noqa: F401
from app.modules.scheduled_payments.models import ScheduledPayment  # noqa: F401
from app.modules.transactions.models import (  # noqa: F401
    Transaction,
    TransferConfirmation,
)
from app.modules.users.models import User  # noqa: F401
