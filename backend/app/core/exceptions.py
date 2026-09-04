"""
Domain exceptions and centralized FastAPI exception handlers.

Rule: services raise domain exceptions (below). Routers never construct
HTTPException directly for business errors — the handlers registered in
main.py translate domain exceptions into the uniform ErrorResponse envelope.
"""
import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("app.errors")


# ---------------------------------------------------------------------------
# Domain exception hierarchy
# ---------------------------------------------------------------------------
class DomainError(Exception):
    """Base class for all business-rule violations."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    error_code: str = "DOMAIN_ERROR"

    def __init__(self, message: str, details: list[str] | None = None):
        self.message = message
        self.details = details or []
        super().__init__(message)


class NotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "NOT_FOUND"


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "CONFLICT"


class UnauthorizedError(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "UNAUTHORIZED"


class ForbiddenError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "FORBIDDEN"


class InvalidCredentialsError(UnauthorizedError):
    error_code = "INVALID_CREDENTIALS"

    def __init__(self) -> None:
        super().__init__("Email or password is incorrect")


class AccountBlockedError(ForbiddenError):
    error_code = "USER_BLOCKED"

    def __init__(self) -> None:
        super().__init__("This user account is blocked")


class EmailAlreadyRegisteredError(ConflictError):
    error_code = "EMAIL_ALREADY_REGISTERED"

    def __init__(self) -> None:
        super().__init__("An account with this email already exists")


class EmailNotVerifiedError(ForbiddenError):
    error_code = "EMAIL_NOT_VERIFIED"

    def __init__(self) -> None:
        super().__init__("Confirm your email with the code we sent before logging in")


class RegistrationAlreadyConfirmedError(ConflictError):
    error_code = "REGISTRATION_ALREADY_CONFIRMED"

    def __init__(self) -> None:
        super().__init__("This email is already verified")


class RegistrationOtpExpiredError(UnauthorizedError):
    error_code = "REGISTRATION_OTP_EXPIRED"

    def __init__(self) -> None:
        super().__init__("This code has expired — request a new one")


class RegistrationOtpInvalidError(UnauthorizedError):
    error_code = "REGISTRATION_OTP_INVALID"

    def __init__(self, attempts_remaining: int) -> None:
        super().__init__(f"That code is incorrect ({attempts_remaining} attempt(s) remaining)")


class RegistrationOtpMaxAttemptsError(ForbiddenError):
    error_code = "REGISTRATION_OTP_MAX_ATTEMPTS"

    def __init__(self) -> None:
        super().__init__("Too many incorrect attempts — request a new code")


class InvalidRefreshTokenError(UnauthorizedError):
    error_code = "INVALID_REFRESH_TOKEN"

    def __init__(self) -> None:
        super().__init__("Refresh token is invalid, expired, or already used")


class InvalidResetTokenError(UnauthorizedError):
    error_code = "INVALID_RESET_TOKEN"

    def __init__(self) -> None:
        super().__init__("Password reset token is invalid, expired, or already used")


class RateLimitExceededError(DomainError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "RATE_LIMIT_EXCEEDED"

    def __init__(self) -> None:
        super().__init__("Too many requests — please try again later")


# ---------------------------------------------------------------------------
# Banking / transfer domain exceptions
# ---------------------------------------------------------------------------
class AccountNotActiveError(ForbiddenError):
    error_code = "ACCOUNT_NOT_ACTIVE"

    def __init__(self, *, which: str = "account") -> None:
        super().__init__(f"The {which} is not active")


class InsufficientBalanceError(ConflictError):
    error_code = "INSUFFICIENT_BALANCE"

    def __init__(self) -> None:
        super().__init__("The sender account does not have sufficient balance")


class SameAccountTransferError(DomainError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "SAME_ACCOUNT_TRANSFER"

    def __init__(self) -> None:
        super().__init__("Cannot transfer money to the same account")


class CurrencyMismatchError(DomainError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "CURRENCY_MISMATCH"

    def __init__(self, expected: str, provided: str) -> None:
        super().__init__(f"The request currency ({provided}) does not match the sender account's currency ({expected})")


class ExchangeRateNotFoundError(ConflictError):
    error_code = "EXCHANGE_RATE_NOT_FOUND"

    def __init__(self, source: str, target: str) -> None:
        super().__init__(f"No active exchange rate available for {source} -> {target}")


class TransactionAlreadyProcessedError(ConflictError):
    error_code = "TRANSACTION_ALREADY_PROCESSED"

    def __init__(self) -> None:
        super().__init__("This transaction has already been confirmed, failed, or reversed")


class TransactionNotReversibleError(ConflictError):
    error_code = "TRANSACTION_NOT_REVERSIBLE"

    def __init__(self, reason: str) -> None:
        super().__init__(f"This transaction cannot be reversed: {reason}")


class OtpExpiredError(UnauthorizedError):
    error_code = "OTP_EXPIRED"

    def __init__(self) -> None:
        super().__init__("The OTP code for this transaction has expired")


class InvalidOtpError(UnauthorizedError):
    error_code = "INVALID_OTP"

    def __init__(self, attempts_remaining: int) -> None:
        super().__init__(
            f"The OTP code is incorrect ({attempts_remaining} attempt(s) remaining)"
        )


class TooManyOtpAttemptsError(ForbiddenError):
    error_code = "TOO_MANY_OTP_ATTEMPTS"

    def __init__(self) -> None:
        super().__init__("Too many incorrect OTP attempts — this transaction has been cancelled")


# ---------------------------------------------------------------------------
# Two-factor authentication (Phase 7)
# ---------------------------------------------------------------------------
class TwoFactorAlreadyEnabledError(ConflictError):
    error_code = "TWO_FACTOR_ALREADY_ENABLED"

    def __init__(self) -> None:
        super().__init__("Two-factor authentication is already enabled on this account")


class TwoFactorNotEnabledError(ConflictError):
    error_code = "TWO_FACTOR_NOT_ENABLED"

    def __init__(self) -> None:
        super().__init__("Two-factor authentication is not enabled on this account")


class TwoFactorSetupNotStartedError(ConflictError):
    error_code = "TWO_FACTOR_SETUP_NOT_STARTED"

    def __init__(self) -> None:
        super().__init__("Call /auth/2fa/setup before attempting to enable two-factor authentication")


class InvalidTotpCodeError(UnauthorizedError):
    error_code = "INVALID_TOTP_CODE"

    def __init__(self) -> None:
        super().__init__("The authenticator code is incorrect or has expired")


class MfaChallengeInvalidError(UnauthorizedError):
    error_code = "INVALID_MFA_CHALLENGE"

    def __init__(self) -> None:
        super().__init__("This login challenge is invalid or has expired — please sign in again")


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
def _error_body(request: Request, error_code: str, message: str, details: list[str]) -> dict:
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    return {
        "error_code": error_code,
        "message": message,
        "details": details,
        "request_id": request_id,
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        logger.warning(
            "domain_error",
            extra={"error_code": exc.error_code, "path": request.url.path},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(request, exc.error_code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in exc.errors()]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_error_body(request, "VALIDATION_ERROR", "Request validation failed", details),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
        logger.error(
            "unhandled_exception",
            exc_info=exc,
            extra={"path": request.url.path, "request_id": request_id},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "details": [],
                "request_id": request_id,
            },
        )
