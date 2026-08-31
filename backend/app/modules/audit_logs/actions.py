"""
Centralized audit action names and outcome status.

Before this module, `write_audit_log_task.delay(...)` call sites across the
codebase wrote action strings as free-form literals (`"LOGIN_SUCCESS"`,
`"CUSTOMER_REGISTERED"`, ...) — functionally fine (every one of them was
spelled consistently), but nothing enforced that, and a typo in a new call
site would silently create an unqueryable, disconnected action name with no
error. This module is the single source of truth going forward; existing
call sites are not being mechanically rewritten wholesale (that touches a
lot of already-correct, already-tested code for no behavioral change), but
every new audit call added as part of this pass uses these constants, and
any future call site should too.

Grouped by the flow that emits them, matching how they show up in the admin
Audit Logs viewer.
"""
from enum import Enum


class AuditStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class AuditAction:
    # --- Registration ---
    CUSTOMER_REGISTERED = "CUSTOMER_REGISTERED"

    # --- Login / session ---
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGIN_BLOCKED = "LOGIN_BLOCKED"
    LOGIN_PASSWORD_OK_AWAITING_MFA = "LOGIN_PASSWORD_OK_AWAITING_MFA"
    MFA_LOGIN_SUCCESS = "MFA_LOGIN_SUCCESS"
    MFA_LOGIN_FAILED = "MFA_LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    REFRESH_TOKEN_REUSE_DETECTED = "REFRESH_TOKEN_REUSE_DETECTED"

    # --- Password / 2FA ---
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    PASSWORD_RESET = "PASSWORD_RESET"
    TWO_FACTOR_ENABLED = "TWO_FACTOR_ENABLED"
    TWO_FACTOR_DISABLED = "TWO_FACTOR_DISABLED"

    # --- Transfers (see app/modules/transactions/service.py) ---
    TRANSFER_INITIATED = "TRANSFER_INITIATED"
    TRANSFER_COMPLETED = "TRANSFER_COMPLETED"
    TRANSFER_FAILED = "TRANSFER_FAILED"
    SCHEDULED_TRANSFER_COMPLETED = "SCHEDULED_TRANSFER_COMPLETED"

    # --- Deposits / withdrawals / cards ---
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    CARD_PAYMENT = "CARD_PAYMENT"
    CUSTOMER_CARD_BLOCKED = "CUSTOMER_CARD_BLOCKED"

    # --- Beneficiaries / profile / scheduled payments ---
    BENEFICIARY_ADDED = "BENEFICIARY_ADDED"
    PROFILE_UPDATED = "PROFILE_UPDATED"
    SCHEDULED_PAYMENT_CREATED = "SCHEDULED_PAYMENT_CREATED"
    SCHEDULED_PAYMENT_CANCELLED = "SCHEDULED_PAYMENT_CANCELLED"

    # --- Admin actions ---
    ADMIN_ACCOUNT_CREATED = "ADMIN_ACCOUNT_CREATED"
    ADMIN_ACCOUNT_STATUS_CHANGED = "ADMIN_ACCOUNT_STATUS_CHANGED"
    ADMIN_CARD_CREATED = "ADMIN_CARD_CREATED"
    ADMIN_CARD_BLOCKED = "ADMIN_CARD_BLOCKED"
    ADMIN_CARD_DELETED = "ADMIN_CARD_DELETED"
    ADMIN_CUSTOMER_CREATED = "ADMIN_CUSTOMER_CREATED"
    ADMIN_CUSTOMER_STATUS_CHANGED = "ADMIN_CUSTOMER_STATUS_CHANGED"
    ADMIN_CUSTOMER_DELETED = "ADMIN_CUSTOMER_DELETED"
    ADMIN_CUSTOMER_RESTORED = "ADMIN_CUSTOMER_RESTORED"
    ADMIN_BENEFICIARY_DELETED = "ADMIN_BENEFICIARY_DELETED"
    ADMIN_BENEFICIARY_RESTORED = "ADMIN_BENEFICIARY_RESTORED"
    ADMIN_TRANSACTION_REVERSED = "ADMIN_TRANSACTION_REVERSED"
    ADMIN_EXCHANGE_RATE_CREATED = "ADMIN_EXCHANGE_RATE_CREATED"
